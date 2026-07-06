#!/usr/bin/env python3
"""Export promoted lessons as a portable pack, or import a pack into this workspace.

Packs carry rules, not data: evidence paths are stripped on export unless
--keep-evidence is passed, and rules are expected to be organization-neutral
(the LESSONS.md format already requires this). Imports are dry-run by default
and merge through the same fuzzy dedupe used by lesson_add.py, so a rule the
workspace already learned is re-confirmed (hits +1) instead of duplicated.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lesson_add import MATCH_THRESHOLD, add_lesson, similarity, split_lessons
from operator_common import load_config, memory_dir, read_text, relpath, resolve_root, write_json

PACK_FORMAT = 1


def export_pack(root: Path, config: dict[str, object], name: str, min_hits: int, keep_evidence: bool, identify: bool) -> dict[str, object]:
    _, entries = split_lessons(read_text(memory_dir(root, config) / "LESSONS.md"))
    lessons = []
    for entry in entries:
        if int(entry["hits"]) < min_hits:
            continue
        lessons.append(
            {
                "rule": str(entry["rule"]),
                "hits": int(entry["hits"]),
                "first_seen": str(entry["date"]),
                "evidence": str(entry["evidence"]) if keep_evidence else "",
            }
        )
    return {
        "format": PACK_FORMAT,
        "name": name,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(config.get("org_name", "workspace")) if identify else "anonymous",
        "kit_version": str(config.get("generated_from_version", "unknown")),
        "min_hits": min_hits,
        "lessons": lessons,
    }


def plan_import(root: Path, config: dict[str, object], pack: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Split pack lessons into (new to this workspace, already known)."""
    _, entries = split_lessons(read_text(memory_dir(root, config) / "LESSONS.md"))
    new: list[dict[str, object]] = []
    known: list[dict[str, object]] = []
    for lesson in pack.get("lessons", []):
        rule = str(lesson.get("rule", "")).strip()
        if not rule:
            continue
        if any(similarity(str(entry["rule"]), rule) >= MATCH_THRESHOLD for entry in entries):
            known.append(lesson)
        else:
            new.append(lesson)
    return new, known


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "import"], help="Export this workspace's lessons or import a pack.")
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--name", default="lesson-pack", help="Pack name (export).")
    parser.add_argument("--min-hits", type=int, default=2, help="Export only lessons re-confirmed at least this many times.")
    parser.add_argument("--keep-evidence", action="store_true", help="Keep evidence paths in the exported pack (default strips them).")
    parser.add_argument("--identify", action="store_true", help="Record the org name as pack source (default: anonymous).")
    parser.add_argument("--out", default="", help="Export path. Defaults to hub/MEMORY/lesson-packs/<name>-<date>.json.")
    parser.add_argument("--pack", default="", help="Pack file to import.")
    parser.add_argument("--execute", action="store_true", help="Apply the import. Without this, print the merge plan.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)

    if args.action == "export":
        pack = export_pack(root, config, args.name, args.min_hits, args.keep_evidence, args.identify)
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out = Path(args.out) if args.out else memory_dir(root, config) / "lesson-packs" / f"{args.name}-{date}.json"
        if not out.is_absolute():
            out = root / out
        write_json(out, pack)
        print(f"Exported {len(pack['lessons'])} lessons (min hits {args.min_hits}) to {relpath(root, out)}")
        if not pack["lessons"]:
            print(f"Note: no lessons met the min-hits threshold; lower it with --min-hits.")
        return 0

    if not args.pack:
        raise SystemExit("import requires --pack <file>")
    pack_path = Path(args.pack)
    if not pack_path.is_absolute():
        pack_path = root / pack_path
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    if pack.get("format") != PACK_FORMAT:
        raise SystemExit(f"unsupported pack format: {pack.get('format')!r} (expected {PACK_FORMAT})")
    provenance = f"pack:{pack.get('name', pack_path.stem)}"
    new, known = plan_import(root, config, pack)

    print(f"# Lesson Pack Import Plan: {pack.get('name')} ({pack.get('source', 'anonymous')})")
    print(f"- Pack lessons: {len(pack.get('lessons', []))}")
    print(f"- New to this workspace: {len(new)}")
    print(f"- Already known (will re-confirm, hits +1): {len(known)}")
    for lesson in new[:20]:
        print(f"- add: {lesson['rule']}")
    if len(new) > 20:
        print(f"- ... {len(new) - 20} more")
    if not args.execute:
        print("- Dry run. Re-run with --execute to merge.")
        return 0

    for lesson in new + known:
        print(add_lesson(root, config, str(lesson["rule"]), provenance))
    print(f"Merged {len(new)} new and re-confirmed {len(known)} existing lessons from {provenance}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
