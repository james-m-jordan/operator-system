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
    heartbeat_status,
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


def automation_heartbeat(root: Path, config: dict[str, object]) -> list[str]:
    """Report last-run recency per enabled automation schedule."""
    statuses = heartbeat_status(root, config)
    lines = []
    for item in statuses:
        if item["status"] == "never-run":
            lines.append(f"- `{item['id']}`: no runs recorded yet (expected every ~{item['max_gap_hours']}h).")
        elif item["status"] == "overdue":
            lines.append(
                f"- `{item['id']}`: OVERDUE - last run {item['last_run']}, {item['age_hours']:.0f}h ago "
                f"(expected every ~{item['max_gap_hours']}h)."
            )
        elif item["status"] == "unreadable":
            lines.append(f"- `{item['id']}`: last run timestamp unreadable ({item['last_run']}).")
        else:
            lines.append(f"- `{item['id']}`: ok - last run {item['last_run']}.")
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
    kit_update = load_json(index_dir / "kit-update.json", {})
    if kit_update.get("adds") or kit_update.get("updates"):
        lines.append(
            f"- Kit update available: {kit_update.get('kit_version_current', '?')} -> "
            f"{kit_update.get('kit_version_available', '?')} "
            f"({kit_update.get('adds', 0)} adds, {kit_update.get('updates', 0)} updates; "
            "run scripts/upgrade_workspace.py from the kit)"
        )
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
