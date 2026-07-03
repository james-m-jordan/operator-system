#!/usr/bin/env python3
"""Build generic work-item and blocker indexes for the operator workspace."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, memory_dir, read_text, relpath, resolve_root, work_item_dir, write_json, write_text


README_NAMES = {"README.md", "readme.md", "Readme.md"}
SOURCE_DIR_NAMES = {"source", "sources", "raw-data", "raw", "input", "inputs"}
METADATA_DIR_NAMES = {"metadata", "meta", "maps"}
OUTPUT_DIR_NAMES = {"analysis", "outputs", "output", "results", "figures"}
BLOCKER_RE = re.compile(r"\b(blocked|blocker|waiting|needs|todo|next action|required)\b", re.IGNORECASE)
EXPLICIT_BLOCKER_RE = re.compile(r"^(blocked|blocker|waiting|todo|next action)\b", re.IGNORECASE)


def first_heading(path: Path) -> str:
    for line in read_text(path).splitlines():
        if line.strip().startswith("#"):
            return line.strip().lstrip("#").strip()
    return ""


def direct_readme(path: Path) -> Path | None:
    for name in README_NAMES:
        candidate = path / name
        if candidate.exists():
            return candidate
    return None


def files_in_named_dirs(path: Path, names: set[str]) -> list[Path]:
    files = []
    for child in path.rglob("*"):
        if not child.is_file() or child.name.startswith("."):
            continue
        rel_parts = child.relative_to(path).parts[:-1]
        if any(part.lower() in names for part in rel_parts):
            files.append(child)
    return sorted(files)


def blocker_lines(path: Path) -> list[dict[str, str]]:
    """Collect deduplicated blocker lines, explicit markers ranked first."""
    explicit: list[dict[str, str]] = []
    inferred: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in [path / "next-actions.md", path / "decisions.md", path / "README.md"]:
        for line in read_text(candidate).splitlines():
            stripped = line.strip()
            if not stripped or not BLOCKER_RE.search(stripped):
                continue
            text = stripped.lstrip("- ").strip()
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            if EXPLICIT_BLOCKER_RE.match(text):
                explicit.append({"text": text, "confidence": "explicit"})
            else:
                inferred.append({"text": text, "confidence": "inferred"})
    return (explicit + inferred)[:20]


def package_status(has_readme: bool, source_count: int, metadata_count: int, output_count: int) -> str:
    if output_count and source_count:
        return "analyzed_or_reviewed"
    if has_readme and source_count and metadata_count:
        return "ready_for_work"
    if has_readme and source_count:
        return "needs_metadata"
    if has_readme:
        return "scaffold"
    return "sparse"


def build_indexes(root: Path, config: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    items = []
    blockers = []
    work_root = work_item_dir(root, config)
    if not work_root.exists():
        return items, blockers, {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "work_item_count": 0}

    for item_dir in sorted(child for child in work_root.iterdir() if child.is_dir() and not child.name.startswith(".")):
        readme = direct_readme(item_dir)
        source_files = files_in_named_dirs(item_dir, SOURCE_DIR_NAMES)
        metadata_files = files_in_named_dirs(item_dir, METADATA_DIR_NAMES)
        output_files = files_in_named_dirs(item_dir, OUTPUT_DIR_NAMES)
        item_blockers = blocker_lines(item_dir)
        status = package_status(bool(readme), len(source_files), len(metadata_files), len(output_files))
        record = {
            "id": item_dir.name,
            "path": relpath(root, item_dir),
            "title": first_heading(readme) if readme else item_dir.name,
            "package_status": status,
            "has_readme": bool(readme),
            "source_file_count": len(source_files),
            "metadata_file_count": len(metadata_files),
            "output_file_count": len(output_files),
            "blocker_count": len(item_blockers),
            "next_actions": [blocker["text"] for blocker in item_blockers[:5]],
        }
        items.append(record)
        for blocker in item_blockers:
            blockers.append(
                {
                    "work_item_id": item_dir.name,
                    "source": record["path"],
                    "text": blocker["text"],
                    "next_action": blocker["text"],
                    "confidence": blocker["confidence"],
                }
            )

    summary = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "work_item_count": len(items),
        "blocker_count": len(blockers),
        "ready_for_work": sum(1 for item in items if item["package_status"] == "ready_for_work"),
        "needs_metadata": sum(1 for item in items if item["package_status"] == "needs_metadata"),
    }
    return items, blockers, summary


def render_summary(summary: dict[str, object], items: list[dict[str, object]]) -> str:
    lines = ["# Memory Index Summary", ""]
    lines.append(f"- Generated: {summary['generated_utc']}")
    lines.append(f"- Work items: {summary['work_item_count']}")
    lines.append(f"- Blockers: {summary['blocker_count']}")
    lines.append(f"- Ready for work: {summary['ready_for_work']}")
    lines.append(f"- Needs metadata: {summary['needs_metadata']}")
    lines.append("")
    lines.append("| work item | status | source | metadata | outputs | blockers |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for item in items:
        lines.append(
            f"| `{item['id']}` | {item['package_status']} | {item['source_file_count']} | "
            f"{item['metadata_file_count']} | {item['output_file_count']} | {item['blocker_count']} |"
        )
    return "\n".join(lines) + "\n"


def validate(items: list[dict[str, object]]) -> list[str]:
    errors = []
    for item in items:
        if not item["path"]:
            errors.append(f"{item['id']}: missing path")
        if item["package_status"] == "ready_for_work" and not item["metadata_file_count"]:
            errors.append(f"{item['id']}: ready_for_work without metadata")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--write", action="store_true", help="Write indexes. Without this, print the summary.")
    parser.add_argument("--validate", action="store_true", help="Validate generated indexes.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    items, blockers, summary = build_indexes(root, config)
    summary_text = render_summary(summary, items)
    if args.write:
        index_dir = memory_dir(root, config) / "indexes"
        write_json(index_dir / "work-item-index.json", items)
        write_json(index_dir / "blocker-index.json", blockers)
        write_json(index_dir / "summary.json", summary)
        write_text(index_dir / "memory-index-summary.md", summary_text)
        print(f"Wrote {index_dir.relative_to(root)}")
    else:
        print(summary_text, end="")

    errors = validate(items) if args.validate else []
    if errors:
        print("Validation errors:")
        for error in errors:
            print(f"- {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
