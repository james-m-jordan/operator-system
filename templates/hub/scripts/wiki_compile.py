#!/usr/bin/env python3
"""Compile hub/wiki/overview.md from memory indexes, lessons, and run history."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import (
    hub_dir,
    load_config,
    memory_dir,
    read_text,
    resolve_root,
    split_action_log,
    write_text,
)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def active_lessons(mem: Path) -> list[str]:
    lessons = []
    in_section = False
    for line in read_text(mem / "LESSONS.md").splitlines():
        if line.startswith("## "):
            in_section = line.strip() == "## Active Lessons"
            continue
        if in_section and line.startswith("- "):
            lessons.append(line)
    return lessons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    mem = memory_dir(root, config)
    index_dir = mem / "indexes"
    items = load_json(index_dir / "work-item-index.json", [])
    health = load_json(index_dir / "memory-health.json", {})
    _, log_entries = split_action_log(read_text(mem / "agent-action-log.md"))
    lessons = active_lessons(mem)

    lines = [f"# {config.get('org_name', 'Workspace')} Overview", ""]
    lines.append(f"- Compiled: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by `hub/scripts/wiki_compile.py`.")
    lines.append(f"- Workspace: {config.get('workspace_name', root.name)}")
    lines.append("")
    lines.append("## Work Items")
    lines.append("")
    if items:
        lines.append("| work item | title | status | blockers |")
        lines.append("| --- | --- | --- | --- |")
        for item in items:
            lines.append(
                f"| `{item.get('id')}` | {str(item.get('title', '-'))[:60]} | "
                f"{item.get('package_status')} | {item.get('blocker_count', 0)} |"
            )
    else:
        lines.append("- No work items indexed yet.")
    lines.append("")
    lines.append("## Active Lessons")
    lines.append("")
    lines.extend(lessons or ["- No active lessons recorded yet."])
    lines.append("")
    lines.append("## Memory Health")
    lines.append("")
    if health:
        status = "ok" if health.get("ok") else "OVER BUDGET"
        lines.append(f"- {health.get('generated_utc', 'unknown')}: {status}")
        for note in health.get("notes", []):
            lines.append(f"- {note}")
    else:
        lines.append("- No snapshot yet.")
    lines.append("")
    lines.append("## Recent Activity")
    lines.append("")
    recent = log_entries[-5:]
    if recent:
        for entry in recent:
            lines.append(entry[0])
    else:
        lines.append("- No action-log entries yet.")
    lines.append("")

    out_path = hub_dir(root, config) / "wiki" / "overview.md"
    write_text(out_path, "\n".join(lines))
    print(f"Wrote {out_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
