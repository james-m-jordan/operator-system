#!/usr/bin/env python3
"""Check whether a generic work package is complete enough to analyze."""

from __future__ import annotations

import argparse
import csv
import re
import json
import subprocess
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


def mapping_coverage(work_item: Path, sources: list[Path], maps: list[Path]) -> tuple[list[str], list[str]]:
    aliases: dict[str, list[Path]] = {}
    for source in sources:
        for key in {source.name, source.relative_to(work_item).as_posix(),
                    source.relative_to(work_item.parent.parent).as_posix()}:
            aliases.setdefault(key, []).append(source)
    covered: set[Path] = set()
    errors = []
    for path in maps:
        if path.suffix.lower() not in {".csv", ".tsv", ".json"}:
            continue
        try:
            if path.suffix.lower() == ".json":
                data = json.loads(path.read_text())
                rows = data if isinstance(data, list) else data.get("files", [data])
            else:
                with path.open(newline="", encoding="utf-8-sig") as handle:
                    rows = list(csv.DictReader(handle, delimiter="\t" if path.suffix.lower() == ".tsv" else ","))
            if not isinstance(rows, list) or not rows:
                raise ValueError("mapping has no rows")
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("each mapping row must be an object")
                value = next((str(row[k]).strip() for k in ("file", "path", "source_file", "stored_path") if row.get(k)), "")
                fields = {**row, **(row.get("extra", {}) if isinstance(row.get("extra"), dict) else {})}
                meaning = next((str(fields[k]).strip() for k in ("meaning", "description", "role", "sample", "sample_id") if fields.get(k)), "")
                matches = aliases.get(value.removeprefix("./"), [])
                if not value or not meaning or len(matches) != 1:
                    raise ValueError(f"row needs an unambiguous source path and meaning: {value!r}")
                covered.add(matches[0])
        except (ValueError, TypeError, AttributeError, OSError, csv.Error) as exc:
            errors.append(f"{path.relative_to(work_item)}: {exc}")
    return [p.relative_to(work_item).as_posix() for p in sources if p not in covered], errors


def evaluate(work_item: Path, profile: str = "evidence") -> dict[str, object]:
    readme = work_item / "README.md"
    readme_text = readme.read_text(encoding="utf-8", errors="replace") if readme.is_file() else ""
    source_files = files_under(work_item, SOURCE_DIR_NAMES)
    metadata_files = sorted(set(files_under(work_item, METADATA_DIR_NAMES) + root_metadata_files(work_item)))
    checks = {
        "work_item_exists": {"ok": work_item.is_dir(), "detail": str(work_item)},
        "readme_exists": {"ok": bool(readme_text.strip()), "detail": "README.md documents package context"},
        "source_files_present": {"ok": bool(source_files), "count": len(source_files)},
        "metadata_present": {"ok": bool(metadata_files), "count": len(metadata_files)},
    }
    if profile == "evidence":
        empty = [p.relative_to(work_item).as_posix() for p in source_files + metadata_files if p.stat().st_size == 0]
        checks["nonempty_files"] = {"ok": not empty, "empty": empty}
        groups = {"owner": ("owner",), "request": ("request", "outcome", "question"),
                  "boundary": ("decision boundary", "constraint", "constraints")}
        fields = {name: any(re.search(r"(?im)^\s*(?:[-*]\s*)?" + re.escape(term) + r"\s*:\s*[^\s]+", readme_text) for term in terms)
                  for name, terms in groups.items()}
        checks["context_fields"] = {"ok": all(fields.values()), "fields": fields}
        uncovered, errors = mapping_coverage(work_item, source_files, metadata_files)
        checks["source_mapping"] = {"ok": bool(source_files) and not uncovered and not errors,
                                     "unmapped": uncovered, "errors": errors}
    missing = [name for name, result in checks.items() if not result["ok"]]
    return {"work_item": str(work_item), "profile": profile, "ok": not missing, "checks": checks, "missing": missing,
            "evidence_limit": "File presence, explicit context, and mapping coverage only; validate domain methods and claims separately.",
            "source_files": [p.as_posix() for p in source_files], "metadata_files": [p.as_posix() for p in metadata_files]}


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
    parser.add_argument("--draft-task", action="store_true", help="When BLOCKED, write a follow-up task draft via task_draft.py.")
    parser.add_argument("--profile", choices=["structure", "evidence"], default="evidence", help="Structure is intake triage only; evidence also checks file coverage and explicit context.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    work_item = Path(args.work_item)
    if not work_item.is_absolute():
        work_item = root / work_item
    result = evaluate(work_item, args.profile)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_markdown(root, result), end="")
    if not result["ok"] and args.draft_task:
        draft = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "task_draft.py"), "--root", str(root), "--work-item", args.work_item],
            capture_output=True,
            text=True,
            check=False,
        )
        if draft.returncode == 0:
            print(f"Task draft created: {draft.stdout.strip()}")
        else:
            print(f"task_draft.py failed ({draft.returncode}): {draft.stderr.strip()[:300]}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
