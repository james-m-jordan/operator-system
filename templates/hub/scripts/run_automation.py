#!/usr/bin/env python3
"""Create a run packet for one automation prompt/spec."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import hub_dir, load_config, memory_dir, read_text, relpath, resolve_root, write_json, write_text


def active_lessons(root: Path, config: dict[str, object]) -> list[str]:
    """Return the Active Lessons bullets from hub/MEMORY/LESSONS.md."""
    lessons = []
    in_section = False
    for line in read_text(memory_dir(root, config) / "LESSONS.md").splitlines():
        if line.startswith("## "):
            in_section = line.strip() == "## Active Lessons"
            continue
        if in_section and line.startswith("- "):
            lessons.append(line)
    return lessons


def load_manifest(root: Path, config: dict[str, object]) -> dict[str, object]:
    path = hub_dir(root, config) / "automations" / "automation-manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def find_automation(manifest: dict[str, object], automation_id: str) -> dict[str, object]:
    for item in manifest.get("automations", []):
        if item.get("id") == automation_id:
            return item
    raise SystemExit(f"unknown automation id: {automation_id}")


def format_list(values: object) -> str:
    if not isinstance(values, list):
        return ""
    return ", ".join(str(value) for value in values)


def build_run_packet(root: Path, config: dict[str, object], automation: dict[str, object], run_id: str) -> tuple[str, dict[str, object]]:
    automation_root = hub_dir(root, config) / "automations"
    prompt_path = automation_root / str(automation["prompt_file"])
    if not prompt_path.exists():
        raise SystemExit(f"missing prompt file: {relpath(root, prompt_path)}")
    prompt = read_text(prompt_path)
    metadata = {
        "run_id": run_id,
        "automation_id": automation["id"],
        "title": automation["title"],
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prompt_file": relpath(root, prompt_path),
        "connectors": automation.get("connectors", []),
        "writes": automation.get("writes", []),
        "closeout": automation.get("closeout", ""),
    }
    lessons = active_lessons(root, config)
    lessons_block = "\n".join(lessons) if lessons else "- No active lessons recorded yet."
    text = (
        f"# Automation Run Packet: {automation['title']}\n\n"
        f"- Run ID: `{run_id}`\n"
        f"- Automation ID: `{automation['id']}`\n"
        f"- Created UTC: {metadata['created_utc']}\n"
        f"- Prompt source: `{metadata['prompt_file']}`\n"
        f"- Connectors: {format_list(metadata['connectors'])}\n"
        f"- Expected writes: {format_list(metadata['writes'])}\n"
        f"- Closeout: {metadata['closeout']}\n\n"
        "## Required Startup\n\n"
        "```bash\n"
        "python3 hub/scripts/preflight_capabilities.py --root .\n"
        "python3 hub/scripts/sync_workspace.py --root .\n"
        "python3 hub/scripts/memory_index_refresh.py --root . --write --validate\n"
        "python3 hub/scripts/state_digest.py --root .\n"
        "python3 hub/scripts/memory_health.py --root . --write\n"
        "```\n\n"
        "## Active Lessons\n\n"
        "Apply these standing lessons from `hub/MEMORY/LESSONS.md` during the run:\n\n"
        f"{lessons_block}\n\n"
        "## Required Closeout\n\n"
        "1. Record the run in `hub/MEMORY/agent-action-log.md`.\n"
        "2. Leave one improvement: add or re-confirm a lesson in\n"
        "   `hub/MEMORY/LESSONS.md`, correct one wrong memory entry, or prune one\n"
        "   stale entry.\n"
        "3. Refresh memory health and fix any budget violation you introduced:\n\n"
        "```bash\n"
        "python3 hub/scripts/memory_health.py --root . --write\n"
        "```\n\n"
        "4. Close the run record so the outcome and improvement are tracked:\n\n"
        "```bash\n"
        f"python3 hub/scripts/run_close.py --root . --run-id {run_id} "
        "--outcome success --improvement lesson --improvement-ref hub/MEMORY/LESSONS.md\n"
        "```\n\n"
        "## Prompt\n\n"
        f"{prompt.rstrip()}\n"
    )
    return text, metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--automation-id", required=True, help="Automation ID from the manifest.")
    parser.add_argument("--print-prompt", action="store_true", help="Print run packet instead of writing it.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    manifest = load_manifest(root, config)
    automation = find_automation(manifest, args.automation_id)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + args.automation_id
    packet_text, metadata = build_run_packet(root, config, automation, run_id)
    if args.print_prompt:
        print(packet_text, end="")
        return 0

    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    run_root = root / str(runtime.get("run_root", "hub/MEMORY/automation-runs"))
    run_dir = run_root / run_id
    write_text(run_dir / "run.md", packet_text)
    write_json(run_dir / "run.json", metadata)
    print(relpath(root, run_dir / "run.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
