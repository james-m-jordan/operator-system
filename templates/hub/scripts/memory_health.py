#!/usr/bin/env python3
"""Measure compact memory surfaces against configured budgets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import (
    SYNC_RISK_LABELS,
    heartbeat_status,
    latest_sync_report,
    load_config,
    load_memory_budgets,
    memory_dir,
    parse_sync_summary,
    read_text,
    resolve_root,
    split_action_log,
    write_json,
)

RECENT_RUN_WINDOW = 20

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def line_count(path: Path) -> int:
    text = read_text(path)
    return len(text.splitlines()) if text else 0


def count_active_lessons(path: Path) -> int:
    count = 0
    in_section = False
    for line in read_text(path).splitlines():
        if line.startswith("## "):
            in_section = line.strip() == "## Active Lessons"
            continue
        if in_section and line.startswith("- "):
            count += 1
    return count


def run_close_stats(root: Path, config: dict[str, object]) -> tuple[int, int, int]:
    """Return (total runs, unclosed runs, recent runs closed without an improvement).

    The no-improvement count covers only the most recent RECENT_RUN_WINDOW runs
    so old history cannot permanently violate the budget.
    """
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    run_root = root / str(runtime.get("run_root", "hub/MEMORY/automation-runs"))
    if not run_root.exists():
        return 0, 0, 0
    run_dirs = sorted(child for child in run_root.iterdir() if (child / "run.json").exists())
    total = len(run_dirs)
    unclosed = no_improvement = 0
    recent = set(str(child) for child in run_dirs[-RECENT_RUN_WINDOW:])
    for child in run_dirs:
        close_path = child / "close.json"
        if not close_path.exists():
            unclosed += 1
            continue
        try:
            close = json.loads(close_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if close.get("improvement", "none") == "none" and str(child) in recent:
            no_improvement += 1
    return total, unclosed, no_improvement


def top_of_mind_ages(path: Path, today: date, max_age_days: int) -> tuple[int, int, int]:
    """Return (dated entries, undated entries, stale dated entries) in Top Of Mind."""
    dated = undated = stale = 0
    in_section = False
    for line in read_text(path).splitlines():
        if line.startswith("## "):
            in_section = line.strip() == "## Top Of Mind"
            continue
        if not in_section or not line.startswith("- "):
            continue
        match = DATE_RE.search(line)
        if not match:
            undated += 1
            continue
        dated += 1
        try:
            entry_date = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if (today - entry_date).days > max_age_days:
            stale += 1
    return dated, undated, stale


def build_report(root: Path, config: dict[str, object]) -> dict[str, object]:
    mem = memory_dir(root, config)
    budgets = load_memory_budgets(config)
    today = datetime.now(timezone.utc).date()

    max_age = budgets["top_of_mind_max_age_days"]
    dated, undated, stale = top_of_mind_ages(mem / "LANDMARKS.md", today, max_age)

    _, log_entries = split_action_log(read_text(mem / "agent-action-log.md"))
    lessons_path = mem / "LESSONS.md"
    active_lessons = count_active_lessons(lessons_path)
    total_runs, unclosed_runs, runs_without_improvement = run_close_stats(root, config)

    checks = [
        {
            "name": "landmarks_lines",
            "value": line_count(mem / "LANDMARKS.md"),
            "budget": budgets["landmarks_max_lines"],
        },
        {
            "name": "state_digest_lines",
            "value": line_count(mem / "state-digest.md"),
            "budget": budgets["state_digest_max_lines"],
        },
        {
            "name": "lessons_lines",
            "value": line_count(lessons_path),
            "budget": budgets["lessons_max_lines"],
        },
        {
            "name": "action_log_entries",
            "value": len(log_entries),
            "budget": budgets["action_log_max_entries"],
        },
        {
            "name": "stale_top_of_mind_entries",
            "value": stale,
            "budget": 0,
            "note": f"dated entries older than {max_age} days",
        },
        {
            "name": "unclosed_automation_runs",
            "value": unclosed_runs,
            "budget": budgets["unclosed_runs_max"],
            "note": "run packets without a close.json outcome record",
        },
        {
            "name": "recent_runs_without_improvement",
            "value": runs_without_improvement,
            "budget": budgets["runs_without_improvement_max"],
            "note": f"closes with improvement=none among the last {RECENT_RUN_WINDOW} runs",
        },
    ]
    for check in checks:
        check["ok"] = check["value"] <= check["budget"]

    violations = [check["name"] for check in checks if not check["ok"]]
    notes = []
    if not lessons_path.exists():
        notes.append("LESSONS.md missing; create it from the starter template.")
    if undated:
        notes.append(f"Top Of Mind has {undated} undated entries; add dates so staleness is measurable.")
    if runs_without_improvement:
        notes.append(
            f"{runs_without_improvement} recent closed runs recorded no improvement; the ratchet expects one per substantive run."
        )
    sync_summary = parse_sync_summary(latest_sync_report(mem))
    sync_risks = {label: sync_summary.get(label, 0) for label in SYNC_RISK_LABELS if sync_summary.get(label, 0)}
    if sync_risks:
        notes.append(
            "Latest repo sync reports risks: "
            + ", ".join(f"{label}={count}" for label, count in sync_risks.items())
            + ". See hub/MEMORY/repo-syncs/."
        )
    overdue = [item["id"] for item in heartbeat_status(root, config) if item["status"] == "overdue"]
    if overdue:
        notes.append("Overdue scheduled automations (advisory): " + ", ".join(overdue) + ".")

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "budgets": budgets,
        "checks": checks,
        "top_of_mind_dated_entries": dated,
        "top_of_mind_undated_entries": undated,
        "active_lessons": active_lessons,
        "automation_runs": total_runs,
        "runs_closed_without_improvement": runs_without_improvement,
        "violations": violations,
        "notes": notes,
        "ok": not violations,
    }


def render_summary(report: dict[str, object]) -> str:
    lines = ["# Memory Health", ""]
    lines.append(f"- Generated: {report['generated_utc']}")
    lines.append(f"- Status: {'ok' if report['ok'] else 'over budget'}")
    lines.append(f"- Active lessons: {report['active_lessons']}")
    lines.append(f"- Automation runs: {report['automation_runs']} ({report['runs_closed_without_improvement']} closed without improvement)")
    lines.append("")
    lines.append("| check | value | budget | ok |")
    lines.append("| --- | --- | --- | --- |")
    for check in report["checks"]:
        lines.append(f"| {check['name']} | {check['value']} | {check['budget']} | {'yes' if check['ok'] else 'NO'} |")
    for note in report["notes"]:
        lines.append(f"- Note: {note}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--write", action="store_true", help="Write the snapshot and append to the history log.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when any budget is violated.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    report = build_report(root, config)
    print(render_summary(report), end="")

    if args.write:
        index_dir = memory_dir(root, config) / "indexes"
        write_json(index_dir / "memory-health.json", report)
        metrics = {check["name"]: check["value"] for check in report["checks"]}
        metrics["active_lessons"] = report["active_lessons"]
        metrics["automation_runs"] = report["automation_runs"]
        metrics["runs_closed_without_improvement"] = report["runs_closed_without_improvement"]
        history_line = {
            "generated_utc": report["generated_utc"],
            "ok": report["ok"],
            "violations": report["violations"],
            "metrics": metrics,
        }
        history_path = index_dir / "memory-health-history.jsonl"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(history_line, sort_keys=True) + "\n")
        print(f"Wrote {index_dir.relative_to(root)}/memory-health.json")

    if args.strict and not report["ok"]:
        print("Budget violations: " + ", ".join(report["violations"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
