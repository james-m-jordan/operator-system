#!/usr/bin/env python3
"""Compile an executive operator report: runs, outcomes, lessons, and the health trend."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lesson_add import split_lessons
from operator_common import (
    heartbeat_status,
    load_config,
    memory_dir,
    read_text,
    relpath,
    resolve_root,
    write_text,
)


def load_jsonl(path: Path) -> list[dict[str, object]]:
    records = []
    for line in read_text(path).splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def runs_in_window(root: Path, config: dict[str, object], cutoff: str) -> tuple[list[dict[str, object]], int]:
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    run_root = root / str(runtime.get("run_root", "hub/MEMORY/automation-runs"))
    closes: list[dict[str, object]] = []
    unclosed = 0
    if not run_root.exists():
        return closes, unclosed
    for child in sorted(run_root.iterdir()):
        if not (child / "run.json").exists():
            continue
        close_path = child / "close.json"
        if not close_path.exists():
            unclosed += 1
            continue
        try:
            close = json.loads(close_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(close.get("closed_utc", "")) >= cutoff:
            closes.append(close)
    return closes, unclosed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--days", type=int, default=30, help="Reporting window in days.")
    parser.add_argument("--write", action="store_true", help="Write the report under hub/MEMORY/reports/. Without this, print it.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    mem = memory_dir(root, config)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=args.days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    closes, unclosed = runs_in_window(root, config, cutoff)
    by_automation = Counter(str(close.get("automation_id", "unknown")) for close in closes)
    by_outcome = Counter(str(close.get("outcome", "unknown")) for close in closes)
    by_improvement = Counter(str(close.get("improvement", "none")) for close in closes)

    _, lessons = split_lessons(read_text(mem / "LESSONS.md"))
    total_hits = sum(int(entry["hits"]) for entry in lessons)

    history = [line for line in load_jsonl(mem / "indexes" / "memory-health-history.jsonl") if str(line.get("generated_utc", "")) >= cutoff]
    trend = ""
    if len(history) >= 2:
        first, last = history[0].get("metrics", {}), history[-1].get("metrics", {})
        deltas = [
            f"{name} {last.get(name, 0) - first.get(name, 0):+d}"
            for name in sorted(set(first) | set(last))
            if last.get(name, 0) != first.get(name, 0)
        ]
        trend = ", ".join(deltas) if deltas else "no change"

    deliveries = list((mem / "outbox-deliveries").rglob("*.json")) if (mem / "outbox-deliveries").exists() else []
    executed_deliveries = 0
    for receipt_path in deliveries:
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if receipt.get("executed") and str(receipt.get("created_utc", "")) >= cutoff:
            executed_deliveries += 1

    heartbeat = heartbeat_status(root, config)
    overdue = [item["id"] for item in heartbeat if item["status"] == "overdue"]

    lines = [f"# Operator Report: {config.get('org_name', 'Workspace')}", ""]
    lines.append(f"- Period: last {args.days} days (since {cutoff[:10]})")
    lines.append(f"- Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"- Kit version: {config.get('generated_from_version', 'unknown')}")
    lines.append("")
    lines.append("## Automation Activity")
    lines.append("")
    lines.append(f"- Closed runs: **{len(closes)}** ({', '.join(f'{k}: {v}' for k, v in sorted(by_outcome.items())) or 'none'})")
    lines.append(f"- Unclosed runs (all time): {unclosed}")
    if by_automation:
        lines.append("")
        lines.append("| automation | closed runs |")
        lines.append("| --- | --- |")
        for automation_id, count in by_automation.most_common():
            lines.append(f"| `{automation_id}` | {count} |")
    lines.append("")
    lines.append("## Improvement Ledger")
    lines.append("")
    lines.append(
        "- Improvements recorded with closes: "
        + (", ".join(f"{k}: {v}" for k, v in sorted(by_improvement.items())) or "none")
    )
    lines.append(f"- Active lessons: **{len(lessons)}** (total re-confirmations: {total_hits})")
    lines.append("- Close records are hash-chained; verify with `python3 hub/scripts/run_close.py --root . --verify-chain`.")
    lines.append("")
    lines.append("## Memory Health Trend")
    lines.append("")
    if trend:
        lines.append(f"- Change across {len(history)} snapshots in window: {trend}")
    else:
        lines.append("- Not enough health snapshots in the window to compute a trend.")
    lines.append("")
    lines.append("## External Activity And Watchdogs")
    lines.append("")
    lines.append(f"- Executed outbox deliveries in window: {executed_deliveries}")
    lines.append("- Overdue scheduled automations: " + (", ".join(f"`{automation_id}`" for automation_id in overdue) or "none"))
    lines.append("")

    report = "\n".join(lines)
    if args.write:
        out = mem / "reports" / f"operator-report-{now.strftime('%Y-%m-%d')}.md"
        write_text(out, report)
        print(f"Wrote {relpath(root, out)}")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
