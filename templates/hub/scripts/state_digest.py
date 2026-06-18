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

from operator_common import load_config, memory_dir, read_text, resolve_root, write_text


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def latest_sync_report(mem: Path) -> Path | None:
    reports = sorted((mem / "repo-syncs").glob("repo-sync-*.md"))
    return reports[-1] if reports else None


def parse_sync_summary(path: Path | None) -> dict[str, int]:
    if not path or not path.exists():
        return {}
    summary: dict[str, int] = {}
    in_summary = False
    for line in read_text(path).splitlines():
        if line == "## Summary":
            in_summary = True
            continue
        if in_summary and line.startswith("## "):
            break
        if in_summary and line.startswith("- "):
            label, _, value = line[2:].partition(":")
            try:
                summary[label.strip()] = int(value.strip())
            except ValueError:
                pass
    return summary


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
            + ", ".join(
                f"{key}:{sync_summary.get(key, 0)}"
                for key in ("Diverged", "Fetch Failed", "Pull Failed", "Reapply Failed", "Hidden Stash State")
            )
        )
    else:
        lines.append("- No sync report found. Run `python3 hub/scripts/sync_workspace.py --root <workspace>`.")
    lines.append("")
    lines.append("## Pointers")
    lines.append("")
    lines.append("- Top-of-mind pointers: `hub/MEMORY/LANDMARKS.md`")
    lines.append("- Work item index: `hub/MEMORY/indexes/work-item-index.json`")
    lines.append("- Blocker index: `hub/MEMORY/indexes/blocker-index.json`")
    lines.append("- Run history: `hub/MEMORY/agent-action-log.md`")
    lines.append("")

    out_path = mem / "state-digest.md"
    write_text(out_path, "\n".join(lines))
    print(f"Wrote {out_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
