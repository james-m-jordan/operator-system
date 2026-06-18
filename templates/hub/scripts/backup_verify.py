#!/usr/bin/env python3
"""Verify source and optional destination paths for a workspace backup."""

from __future__ import annotations

import argparse
from datetime import date
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, memory_dir, relpath, resolve_root, write_text


DEFAULT_REQUIRED_PATHS = ["AGENTS.md", "hub", "work-items", "knowledge-base"]


def path_status(base: Path, relative: str) -> dict[str, object]:
    path = base / relative
    return {
        "path": relative,
        "exists": path.exists(),
        "type": "directory" if path.is_dir() else "file" if path.is_file() else "missing",
    }


def render_report(root: Path, destination: Path | None, required: list[str], source_status, dest_status) -> str:
    lines = ["# Backup Verification Report", ""]
    lines.append(f"- Date: {date.today().isoformat()}")
    lines.append(f"- Source: `{root}`")
    lines.append(f"- Destination: `{destination}`" if destination else "- Destination: not checked")
    lines.append("")
    lines.append("## Source Required Paths")
    lines.append("")
    for item in source_status:
        lines.append(f"- {'PASS' if item['exists'] else 'FAIL'} `{item['path']}` ({item['type']})")
    if dest_status is not None:
        lines.append("")
        lines.append("## Destination Required Paths")
        lines.append("")
        for item in dest_status:
            lines.append(f"- {'PASS' if item['exists'] else 'FAIL'} `{item['path']}` ({item['type']})")
    source_ok = all(item["exists"] for item in source_status)
    dest_ok = dest_status is None or all(item["exists"] for item in dest_status)
    lines.append("")
    lines.append(f"## Result\n\n{'PASS' if source_ok and dest_ok else 'BLOCKED'}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--destination", default="", help="Optional backup destination to verify.")
    parser.add_argument("--write-report", action="store_true", help="Write report under hub/MEMORY/backups/.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    backup_config = config.get("backup", {}) if isinstance(config.get("backup"), dict) else {}
    required = backup_config.get("required_paths") or DEFAULT_REQUIRED_PATHS
    source_status = [path_status(root, item) for item in required]
    destination = Path(args.destination).expanduser().resolve() if args.destination else None
    dest_status = [path_status(destination, item) for item in required] if destination else None
    report = render_report(root, destination, required, source_status, dest_status)
    if args.write_report:
        out = memory_dir(root, config) / "backups" / f"backup-verify-{date.today().isoformat()}.md"
        write_text(out, report)
        print(out)
    else:
        print(report, end="")
    ok = all(item["exists"] for item in source_status) and (dest_status is None or all(item["exists"] for item in dest_status))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
