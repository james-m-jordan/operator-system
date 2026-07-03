#!/usr/bin/env python3
"""Generate a compact current-state digest from generic memory indexes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import (
    SYNC_RISK_LABELS,
    latest_sync_report,
    load_config,
    memory_dir,
    parse_sync_summary,
    read_text,
    resolve_root,
    write_text,
)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def health_trend(history_path: Path) -> str:
    """Compare the two most recent health snapshots and describe the deltas."""
    lines = [line for line in read_text(history_path).splitlines() if line.strip()]
    if len(lines) < 2:
        return ""
    try:
        previous = json.loads(lines[-2]).get("metrics", {})
        current = json.loads(lines[-1]).get("metrics", {})
    except Exception:
        return ""
    deltas = []
    for name in sorted(set(previous) | set(current)):
        change = current.get(name, 0) - previous.get(name, 0)
        if change:
            deltas.append(f"{name} {'+' if change > 0 else ''}{change}")
    return ", ".join(deltas) if deltas else "no change"


def cron_max_gap_hours(cron: str) -> int:
    """Coarse expected max gap between runs for a cron expression."""
    fields = cron.split()
    if len(fields) != 5:
        return 26
    _, hour, day_of_month, _, day_of_week = fields
    if day_of_month != "*":
        return 32 * 24
    if day_of_week != "*":
        return 8 * 24
    if hour != "*":
        return 26
    return 3


def automation_heartbeat(root: Path, config: dict[str, object]) -> list[str]:
    """Report last-run recency per enabled automation schedule."""
    schedules = config.get("automation_schedules", {})
    if not isinstance(schedules, dict) or not schedules:
        return ["- No automation schedules configured."]
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    run_root = root / str(runtime.get("run_root", "hub/MEMORY/automation-runs"))
    last_run: dict[str, str] = {}
    if run_root.exists():
        for child in sorted(run_root.iterdir()):
            meta = load_json(child / "run.json", {})
            automation_id = str(meta.get("automation_id", ""))
            created = str(meta.get("created_utc", ""))
            if automation_id and created > last_run.get(automation_id, ""):
                last_run[automation_id] = created
    now = datetime.now(timezone.utc)
    lines = []
    for automation_id, schedule in sorted(schedules.items()):
        if not isinstance(schedule, dict) or not schedule.get("enabled"):
            continue
        max_gap = schedule.get("max_gap_hours") or cron_max_gap_hours(str(schedule.get("cron", "")))
        last = last_run.get(automation_id)
        if not last:
            lines.append(f"- `{automation_id}`: no runs recorded yet (expected every ~{max_gap}h).")
            continue
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age_hours = (now - last_dt).total_seconds() / 3600
        except ValueError:
            lines.append(f"- `{automation_id}`: last run timestamp unreadable ({last}).")
            continue
        if age_hours > max_gap:
            lines.append(f"- `{automation_id}`: OVERDUE - last run {last}, {age_hours:.0f}h ago (expected every ~{max_gap}h).")
        else:
            lines.append(f"- `{automation_id}`: ok - last run {last}.")
    return lines or ["- No enabled automation schedules."]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    mem = memory_dir(root, config)
    index_dir = mem / "indexes"
    items = load_json(index_dir / "work-item-index.json", [])
    blockers = load_json(index_dir / "blocker-index.json", [])
    caps = load_json(mem / "capabilities.json", {})
    sync_report = latest_sync_report(mem)
    sync_summary = parse_sync_summary(sync_report)

    status_counts = Counter(item.get("package_status", "unknown") for item in items)
    cap_checks = caps.get("checks", {}) if isinstance(caps, dict) else {}
    cap_line = ", ".join(
        f"{name}={'ok' if isinstance(value, dict) and value.get('ok') else 'DOWN'}"
        for name, value in cap_checks.items()
        if name != "connectors"
    ) or "no capability snapshot"

    lines = ["# State Digest", ""]
    lines.append(f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `hub/scripts/state_digest.py`.")
    lines.append(f"- Organization: {config.get('org_name', 'Unknown')}")
    lines.append(f"- Workspace: {config.get('workspace_name', root.name)}")
    lines.append(f"- Capabilities: {cap_line}")
    if caps.get("required_down"):
        lines.append(f"- Required capabilities down: {', '.join(caps['required_down'])}")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append(f"- Work items: **{len(items)}**")
    lines.append(f"- Blockers/next actions: **{len(blockers)}**")
    lines.append("- Package status mix: " + (", ".join(f"{key}:{value}" for key, value in status_counts.items()) or "none"))
    lines.append("")
    lines.append("## Work Items")
    lines.append("")
    lines.append("| work item | title | status | source | metadata | outputs | first next action |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for item in items[:30]:
        next_actions = item.get("next_actions") or []
        first = str(next_actions[0]) if next_actions else "-"
        lines.append(
            f"| `{item.get('id')}` | {str(item.get('title', '-'))[:80]} | {item.get('package_status')} | {item.get('source_file_count')} | "
            f"{item.get('metadata_file_count')} | {item.get('output_file_count')} | {first[:120]} |"
        )
    lines.append("")
    lines.append("## Repo Sync Health")
    lines.append("")
    if sync_report:
        lines.append(f"- Latest sync: `{sync_report.relative_to(root)}`")
        lines.append(
            "- Sync risks: "
            + ", ".join(f"{key}:{sync_summary.get(key, 0)}" for key in SYNC_RISK_LABELS)
        )
    else:
        lines.append("- No sync report found. Run `python3 hub/scripts/sync_workspace.py --root <workspace>`.")
    lines.append("")
    lines.append("## Memory Health")
    lines.append("")
    health = load_json(index_dir / "memory-health.json", {})
    if health:
        status = "ok" if health.get("ok") else "OVER BUDGET"
        lines.append(f"- Snapshot: {health.get('generated_utc', 'unknown')} - {status}")
        violations = health.get("violations") or []
        if violations:
            lines.append(f"- Violations: {', '.join(violations)}")
        metrics = ", ".join(
            f"{check.get('name')}={check.get('value')}/{check.get('budget')}"
            for check in health.get("checks", [])
        )
        if metrics:
            lines.append(f"- Budgets: {metrics}")
    else:
        lines.append("- No memory-health snapshot yet. Run `python3 hub/scripts/memory_health.py --root . --write`.")
    trend = health_trend(index_dir / "memory-health-history.jsonl")
    if trend:
        lines.append(f"- Trend vs previous snapshot: {trend}")
    lines.append("")
    lines.append("## Automation Heartbeat")
    lines.append("")
    lines.extend(automation_heartbeat(root, config))
    lines.append("")
    lines.append("## Pointers")
    lines.append("")
    lines.append("- Top-of-mind pointers: `hub/MEMORY/LANDMARKS.md`")
    lines.append("- Reusable lessons: `hub/MEMORY/LESSONS.md`")
    lines.append("- Work item index: `hub/MEMORY/indexes/work-item-index.json`")
    lines.append("- Blocker index: `hub/MEMORY/indexes/blocker-index.json`")
    lines.append("- Memory health trend: `hub/MEMORY/indexes/memory-health-history.jsonl`")
    lines.append("- Run history: `hub/MEMORY/agent-action-log.md`")
    lines.append("")

    out_path = mem / "state-digest.md"
    write_text(out_path, "\n".join(lines))
    print(f"Wrote {out_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
