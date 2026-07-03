#!/usr/bin/env python3
"""Retire old runtime artifacts from hub/MEMORY into the archive. Dry-run by default."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, memory_dir, relpath, resolve_root, workspace_lock

DEFAULT_RETENTION_DAYS = 90
DEFAULT_TARGETS = [
    "automation-runs",
    "outbox-deliveries",
    "repo-syncs",
    "morning",
    "feed-digests",
    "backups",
]
NAME_DATE_RE = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})")


def retention_settings(config: dict[str, object]) -> tuple[int, list[str]]:
    retention = config.get("retention", {}) if isinstance(config.get("retention"), dict) else {}
    days = retention.get("days") if isinstance(retention.get("days"), int) else DEFAULT_RETENTION_DAYS
    targets = retention.get("targets") if isinstance(retention.get("targets"), list) else DEFAULT_TARGETS
    return days, [str(target) for target in targets]


def artifact_date(path: Path) -> date:
    """Best-effort artifact date: parseable date in the name, else mtime."""
    match = NAME_DATE_RE.search(path.name)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date()


def collect_expired(mem: Path, targets: list[str], cutoff: date) -> list[Path]:
    expired = []
    for target in targets:
        target_dir = mem / target
        if not target_dir.exists():
            continue
        for child in sorted(target_dir.iterdir()):
            if child.name.startswith(".") or child.name.lower() == "readme.md":
                continue
            if child.is_dir() and target in {"outbox-deliveries", "morning"}:
                # publisher/date subfolders: sweep their children individually
                for grandchild in sorted(child.iterdir()):
                    if artifact_date(grandchild) < cutoff:
                        expired.append(grandchild)
                continue
            if artifact_date(child) < cutoff:
                expired.append(child)
    return expired


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--days", type=int, default=0, help="Retention window; defaults to retention.days config (90).")
    parser.add_argument("--delete", action="store_true", help="Delete expired artifacts instead of archiving them.")
    parser.add_argument("--execute", action="store_true", help="Apply the sweep. Without this, print the plan.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    days, targets = retention_settings(config)
    if args.days > 0:
        days = args.days
    mem = memory_dir(root, config)
    today = datetime.now(timezone.utc).date()
    cutoff = date.fromordinal(today.toordinal() - days)
    expired = collect_expired(mem, targets, cutoff)

    print("# Retention Sweep Plan")
    print(f"- Retention: {days} days (artifacts dated before {cutoff.isoformat()})")
    print(f"- Targets: {', '.join(targets)}")
    print(f"- Expired artifacts: {len(expired)}")
    for path in expired[:50]:
        print(f"- {'delete' if args.delete else 'archive'}: {relpath(root, path)}")
    if len(expired) > 50:
        print(f"- ... {len(expired) - 50} more")
    if not expired:
        print("- Nothing to retire.")
        return 0
    if not args.execute:
        print("- Dry run. Re-run with --execute to apply.")
        return 0

    with workspace_lock(root, config, name="retention"):
        retired_root = mem / "archive" / "retired"
        moved = 0
        for path in expired:
            if args.delete:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
            else:
                destination = retired_root / relpath(mem, path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(destination))
            moved += 1
    action = "Deleted" if args.delete else "Archived"
    print(f"{action} {moved} artifacts" + ("" if args.delete else f" under {relpath(root, retired_root)}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
