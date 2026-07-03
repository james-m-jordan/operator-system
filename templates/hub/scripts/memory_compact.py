#!/usr/bin/env python3
"""Rotate old agent-action-log entries into the memory archive. Dry-run by default."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import (
    action_log_entry_date,
    load_config,
    load_memory_budgets,
    memory_dir,
    read_text,
    relpath,
    resolve_root,
    split_action_log,
    write_text,
)


def plan_rotation(entries: list[list[str]], keep: int) -> tuple[list[list[str]], list[list[str]]]:
    """Split entries into (retained, archived).

    Entries are kept in file order (oldest first, newest appended last). The
    newest `keep` entries stay; older dated entries rotate to the archive.
    Undated entries are always retained because their age is unknown.
    """
    if len(entries) <= keep:
        return list(entries), []
    retained: list[list[str]] = []
    archived: list[list[str]] = []
    for index, entry in enumerate(entries):
        if index >= len(entries) - keep or not action_log_entry_date(entry):
            retained.append(entry)
        else:
            archived.append(entry)
    return retained, archived


def entry_text(entry: list[str]) -> str:
    return "\n".join(entry).rstrip()


def append_archive(archive_dir: Path, archived: list[list[str]]) -> list[Path]:
    by_year: dict[str, list[list[str]]] = defaultdict(list)
    for entry in archived:
        year = action_log_entry_date(entry)[:4]
        by_year[year].append(entry)
    touched = []
    for year in sorted(by_year):
        path = archive_dir / f"action-log-{year}.md"
        existing = read_text(path)
        if not existing:
            existing = f"# Agent Action Log Archive {year}\n\nRotated from `hub/MEMORY/agent-action-log.md`.\n\n## Log\n"
        body = existing.rstrip() + "\n\n" + "\n".join(entry_text(entry) for entry in by_year[year]) + "\n"
        write_text(path, body)
        touched.append(path)
    return touched


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--keep", type=int, default=0, help="Entries to keep; defaults to the action_log_max_entries budget.")
    parser.add_argument("--execute", action="store_true", help="Rewrite the log and archive files. Without this, print the plan.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    budgets = load_memory_budgets(config)
    keep = args.keep if args.keep > 0 else budgets["action_log_max_entries"]

    mem = memory_dir(root, config)
    log_path = mem / "agent-action-log.md"
    preamble, entries = split_action_log(read_text(log_path))
    retained, archived = plan_rotation(entries, keep)

    print("# Action Log Rotation Plan")
    print(f"- Log: {relpath(root, log_path)}")
    print(f"- Entries: {len(entries)}, keep budget: {keep}")
    print(f"- Retained: {len(retained)}, to archive: {len(archived)}")
    if not archived:
        print("- Nothing to rotate.")
        return 0
    years = sorted({action_log_entry_date(entry)[:4] for entry in archived})
    print(f"- Archive files: {', '.join('hub/MEMORY/archive/action-log-' + year + '.md' for year in years)}")

    if not args.execute:
        print("- Dry run. Re-run with --execute to rotate.")
        return 0

    touched = append_archive(mem / "archive", archived)
    new_log = "\n".join(preamble).rstrip() + "\n\n" + "\n".join(entry_text(entry) for entry in retained) + "\n"
    write_text(log_path, new_log)
    for path in touched:
        print(f"Updated {relpath(root, path)}")
    print(f"Rewrote {relpath(root, log_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
