#!/usr/bin/env python3
"""Add, re-confirm, or prune lessons in hub/MEMORY/LESSONS.md."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, load_memory_budgets, memory_dir, read_text, resolve_root, workspace_lock, write_text, write_json

ENTRY_RE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+?)\s*\|\s*evidence:\s*(.+?)\s*\|\s*hits:\s*(\d+)\s*$")
MATCH_THRESHOLD = 0.8


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def split_lessons(text: str) -> tuple[list[str], list[dict[str, object]]]:
    """Split LESSONS.md into (header lines, parsed Active Lessons entries)."""
    header: list[str] = []
    entries: list[dict[str, object]] = []
    in_section = False
    for line in text.splitlines():
        if not in_section:
            header.append(line)
            if line.strip() == "## Active Lessons":
                in_section = True
            continue
        match = ENTRY_RE.match(line.strip())
        if match:
            entries.append(
                {"date": match.group(1), "rule": match.group(2), "evidence": match.group(3), "hits": int(match.group(4))}
            )
        elif line.strip().startswith("- "):
            entries.append({"date": "", "rule": line.strip().lstrip("- ").strip(), "evidence": "", "hits": 1})
    return header, entries


def render(header: list[str], entries: list[dict[str, object]]) -> str:
    lines = list(header)
    lines.append("")
    for entry in entries:
        date = entry["date"] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        evidence = entry["evidence"] or "-"
        lines.append(f"- {date} | {entry['rule']} | evidence: {evidence} | hits: {entry['hits']}")
    return "\n".join(lines).rstrip() + "\n"


def add_lesson(root: Path, config: dict[str, object], rule: str, evidence: str, distinct: bool = False) -> str:
    """Confirm exact rules only, once per evidence reference; flag near matches."""
    if not rule.strip() or any(char in rule + evidence for char in "\n\r|"):
        raise SystemExit("rule/evidence must be nonempty single-line text without pipes")
    lessons_path = memory_dir(root, config) / "LESSONS.md"
    with workspace_lock(root, config, name="lessons"):
        text = read_text(lessons_path)
        if not text:
            raise SystemExit(f"missing {lessons_path}; scaffold LESSONS.md first")
        header, entries = split_lessons(text)
        exact = next((entry for entry in entries if normalize(str(entry["rule"])) == normalize(rule)), None)
        near = [entry for entry in entries if similarity(str(entry["rule"]), rule) >= MATCH_THRESHOLD]
        if not exact and near and not distinct:
            raise SystemExit("similar lesson has different wording; review for contradiction before using --distinct: " + str(near[0]["rule"]))
        if not evidence.strip():
            if exact:
                return "unchanged lesson: no new evidence supplied"
            raise SystemExit("new lessons require --evidence")
        evidence_path = memory_dir(root, config) / "indexes/lesson-evidence.json"
        registry = json.loads(read_text(evidence_path) or "{}")
        identity = hashlib.sha256(normalize(rule).encode()).hexdigest()
        known = registry.setdefault(identity, [])
        if exact and exact["evidence"] and exact["evidence"] not in known:
            known.append(exact["evidence"])
        if exact and evidence in known:
            return "unchanged lesson: evidence already recorded"
        known.append(evidence)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if exact:
            exact["hits"] = int(exact["hits"]) + 1
            exact["evidence"] = evidence
            result = f"re-confirmed existing lesson (hits: {exact['hits']}): {exact['rule']}"
        else:
            entries.append({"date": today, "rule": rule.strip(), "evidence": evidence.strip(), "hits": 1})
            result = f"added new lesson: {rule.strip()}"
        # Persist the lesson first; its current evidence also makes retry idempotent.
        write_text(lessons_path, render(header, entries))
        write_json(evidence_path, registry)
        return result


def prune_lesson(root: Path, config: dict[str, object], match_text: str) -> str:
    lessons_path = memory_dir(root, config) / "LESSONS.md"
    with workspace_lock(root, config, name="lessons"):
        header, entries = split_lessons(read_text(lessons_path))
        matches = [entry for entry in entries if normalize(str(entry["rule"])) == normalize(match_text)]
        if len(matches) != 1:
            raise SystemExit("pruning requires the exact rule text; fuzzy deletion is disabled")
        removed = matches[0]
        entries.remove(removed)
        write_text(lessons_path, render(header, entries))
        return f"pruned lesson (had {removed['hits']} hits): {removed['rule']}"


def budget_warning(root: Path, config: dict[str, object]) -> str:
    lessons_path = memory_dir(root, config) / "LESSONS.md"
    budget = load_memory_budgets(config)["lessons_max_lines"]
    lines = len(read_text(lessons_path).splitlines())
    if lines > budget:
        return f"Warning: LESSONS.md is {lines} lines (budget {budget}); consolidate or prune."
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--rule", default="", help="Lesson text to add or re-confirm.")
    parser.add_argument("--evidence", default="", help="Path or pointer supporting the lesson.")
    parser.add_argument("--prune", default="", help="Remove the lesson best matching this text.")
    parser.add_argument("--distinct", action="store_true", help="After review, add a similar but intentionally distinct rule.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    if args.prune:
        print(prune_lesson(root, config, args.prune))
    elif args.rule:
        print(add_lesson(root, config, args.rule, args.evidence, args.distinct))
    else:
        raise SystemExit("pass --rule (with optional --evidence) or --prune")
    warning = budget_warning(root, config)
    if warning:
        print(warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
