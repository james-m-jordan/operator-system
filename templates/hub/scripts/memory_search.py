#!/usr/bin/env python3
"""Search durable memory, knowledge base, and archives for keywords."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import hub_dir, load_config, memory_dir, read_text, relpath, resolve_root, work_item_dir

SEARCHABLE_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".csv"}
MAX_SNIPPET_LENGTH = 160
MAX_LINES_PER_FILE = 3


def search_roots(root: Path, config: dict[str, object], include_work_items: bool) -> list[Path]:
    roots = [
        memory_dir(root, config),
        hub_dir(root, config) / "wiki",
        root / str(config.get("knowledge_base_root", "knowledge-base")),
    ]
    if include_work_items:
        roots.append(work_item_dir(root, config))
    return [path for path in roots if path.exists()]


def score_file(path: Path, text: str, terms: list[str]) -> tuple[int, list[tuple[int, str]]]:
    lower = text.lower()
    score = 0
    for term in terms:
        occurrences = lower.count(term)
        score += occurrences
        if term in path.name.lower():
            score += 5
    if not score:
        return 0, []
    matches: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        line_lower = line.lower()
        if any(term in line_lower for term in terms):
            snippet = line.strip()
            if len(snippet) > MAX_SNIPPET_LENGTH:
                snippet = snippet[: MAX_SNIPPET_LENGTH - 3] + "..."
            matches.append((number, snippet))
            if len(matches) >= MAX_LINES_PER_FILE:
                break
    return score, matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--query", required=True, help="Space-separated search terms.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum files to report.")
    parser.add_argument("--include-work-items", action="store_true", help="Also search work-items/.")
    args = parser.parse_args()

    terms = [term.lower() for term in args.query.split() if term.strip()]
    if not terms:
        raise SystemExit("empty query")

    root = resolve_root(args.root)
    config = load_config(root)

    results = []
    for search_root in search_roots(root, config, args.include_work_items):
        for path in sorted(search_root.rglob("*")):
            if not path.is_file() or path.name.startswith(".") or path.suffix.lower() not in SEARCHABLE_SUFFIXES:
                continue
            score, matches = score_file(path, read_text(path), terms)
            if score:
                results.append((score, path, matches))

    results.sort(key=lambda item: (-item[0], relpath(root, item[1])))
    if not results:
        print(f"No matches for: {args.query}")
        return 0

    print(f"# Memory Search: {args.query}")
    print(f"- Files matched: {len(results)} (showing up to {args.limit})")
    print("")
    for score, path, matches in results[: args.limit]:
        print(f"## {relpath(root, path)} (score {score})")
        for number, snippet in matches:
            print(f"- {number}: {snippet}")
        print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
