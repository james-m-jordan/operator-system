#!/usr/bin/env python3
"""Create a no-terminal collaborator task draft for a work item."""

from __future__ import annotations

import argparse
from datetime import date
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, memory_dir, read_text, relpath, resolve_root, work_item_dir, write_text


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return value.lower() or "task"


def first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith("#"):
            return line.strip().lstrip("#").strip()
    return fallback


def next_actions(work_item: Path) -> list[str]:
    text = read_text(work_item / "next-actions.md")
    actions = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("- ").strip()
        if stripped:
            actions.append(stripped)
    return actions


def build_draft(root: Path, work_item: Path, assignee: str, title: str, action: str) -> str:
    readme = read_text(work_item / "README.md")
    inferred_title = first_heading(readme, work_item.name)
    draft_title = title or f"Next steps for {inferred_title}"
    actions = next_actions(work_item)
    primary_action = action or (actions[0] if actions else "Add the missing package context, source files, or metadata described below.")
    package_gate_cmd = f"python3 hub/scripts/package_gate.py --root . --work-item {relpath(root, work_item)}"
    lines = [
        f"# {draft_title}",
        "",
        f"- Work item: `{relpath(root, work_item)}`",
        f"- Assignee: {assignee or 'TBD'}",
        f"- Draft date: {date.today().isoformat()}",
        "",
        "## Request",
        "",
        "Please complete the package so the operator agent can proceed without guessing.",
        "",
        "## Next Steps",
        "",
        f"1. {primary_action}",
        f"2. Add or update source files under `{relpath(root, work_item)}/source/`.",
        f"3. Add metadata under `{relpath(root, work_item)}/metadata/` that explains each source file, row, sheet, attachment, or message.",
        "4. Update the work-item `README.md` with owner, requested outcome, constraints, and decision boundary.",
        f"5. Ask the operator agent to rerun `{package_gate_cmd}`.",
        "",
        "## Notes For The Agent",
        "",
        "- Keep this as a draft until a human chooses the delivery channel.",
        "- Do not send external messages or change permissions from this draft alone.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--work-item", required=True, help="Work-item ID or path.")
    parser.add_argument("--assignee", default="", help="Optional assignee.")
    parser.add_argument("--title", default="", help="Optional draft title.")
    parser.add_argument("--action", default="", help="Optional first numbered action.")
    parser.add_argument("--out", default="", help="Optional output path.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    candidate = Path(args.work_item)
    if not candidate.is_absolute():
        if (root / candidate).exists():
            candidate = root / candidate
        else:
            candidate = work_item_dir(root, config) / args.work_item
    candidate = candidate.resolve()
    text = build_draft(root, candidate, args.assignee, args.title, args.action)
    out = Path(args.out) if args.out else memory_dir(root, config) / "task-drafts" / f"{date.today().isoformat()}-{slugify(candidate.name)}.md"
    if not out.is_absolute():
        out = root / out
    write_text(out, text)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
