#!/usr/bin/env python3
"""Check whether a generic work package is complete enough to analyze."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import relpath, resolve_root


SOURCE_DIR_NAMES = {"source", "sources", "raw-data", "raw", "input", "inputs"}
METADATA_DIR_NAMES = {"metadata", "meta", "maps"}
IGNORED_NAMES = {"README.md", "readme.md", ".DS_Store"}
CONTEXT_TERMS = ("owner", "request", "outcome", "context", "question", "decision", "constraint")


def files_under(path: Path, dir_names: set[str]) -> list[Path]:
    files: list[Path] = []
    for child in path.rglob("*"):
        if not child.is_file() or child.name in IGNORED_NAMES:
            continue
        if any(part.lower() in dir_names for part in child.relative_to(path).parts[:-1]):
            files.append(child)
    return sorted(files)


def root_metadata_files(path: Path) -> list[Path]:
    candidates = []
    for child in (path.iterdir() if path.exists() else []):
        if child.is_file() and any(token in child.name.lower() for token in ("metadata", "sample", "map", "index")):
            candidates.append(child)
    return sorted(candidates)


def evaluate(work_item: Path) -> dict[str, object]:
    readme = work_item / "README.md"
    readme_text = readme.read_text(encoding="utf-8", errors="replace") if readme.exists() else ""
    source_files = files_under(work_item, SOURCE_DIR_NAMES)
    metadata_files = files_under(work_item, METADATA_DIR_NAMES) + root_metadata_files(work_item)

    checks = {
        "work_item_exists": {"ok": work_item.exists(), "detail": str(work_item)},
        "readme_exists": {"ok": readme.exists(), "detail": "README.md documents package context"},
        "source_files_present": {"ok": bool(source_files), "count": len(source_files)},
        "metadata_present": {"ok": bool(metadata_files), "count": len(metadata_files)},
        "context_terms_present": {
            "ok": sum(1 for term in CONTEXT_TERMS if term in readme_text.lower()) >= 2,
            "matched_terms": [term for term in CONTEXT_TERMS if term in readme_text.lower()],
        },
    }
    missing = [name for name, result in checks.items() if not result["ok"]]
    return {
        "work_item": str(work_item),
        "ok": not missing,
        "checks": checks,
        "missing": missing,
        "source_files": [path.as_posix() for path in source_files],
        "metadata_files": [path.as_posix() for path in metadata_files],
    }


def render_markdown(root: Path, result: dict[str, object]) -> str:
    lines = ["# Work Package Gate", ""]
    lines.append(f"- Work item: `{relpath(root, Path(result['work_item']))}`")
    lines.append(f"- Status: {'PASS' if result['ok'] else 'BLOCKED'}")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    for name, check in result["checks"].items():
        lines.append(f"- {'PASS' if check['ok'] else 'FAIL'} `{name}`")
    if result["missing"]:
        lines.append("")
        lines.append("## Missing")
        lines.append("")
        lines.extend(f"- `{name}`" for name in result["missing"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--work-item", required=True, help="Work-item path to check.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    work_item = Path(args.work_item)
    if not work_item.is_absolute():
        work_item = root / work_item
    result = evaluate(work_item)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_markdown(root, result), end="")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
