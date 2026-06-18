#!/usr/bin/env python3
"""Install automation prompt/spec bundles from the generated manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import hub_dir, load_config, read_text, relpath, resolve_root, write_json, write_text


def load_manifest(root: Path, config: dict[str, object]) -> dict[str, object]:
    manifest = hub_dir(root, config) / "automations" / "automation-manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8"))


def install(root: Path, destination: Path, selected: set[str] | None = None) -> list[Path]:
    config = load_config(root)
    manifest = load_manifest(root, config)
    automation_root = hub_dir(root, config) / "automations"
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for automation in manifest.get("automations", []):
        automation_id = automation["id"]
        if selected and automation_id not in selected:
            continue
        prompt_path = automation_root / automation["prompt_file"]
        prompt_text = read_text(prompt_path)
        target_dir = destination / automation_id
        target_dir.mkdir(parents=True, exist_ok=True)
        spec = dict(automation)
        spec["prompt"] = prompt_text
        spec["source_manifest"] = relpath(root, automation_root / "automation-manifest.json")
        write_json(target_dir / "automation.json", spec)
        write_text(
            target_dir / "automation.md",
            f"# {automation['title']}\n\n"
            f"- ID: `{automation_id}`\n"
            f"- Cadence: {automation.get('cadence', '')}\n"
            f"- Connectors: {', '.join(automation.get('connectors', []))}\n"
            f"- Closeout: {automation.get('closeout', '')}\n\n"
            f"## Prompt\n\n{prompt_text.rstrip()}\n",
        )
        written.extend([target_dir / "automation.json", target_dir / "automation.md"])
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--out", default=".operator-automations", help="Destination folder for installed automation specs.")
    parser.add_argument("--only", nargs="*", default=[], help="Optional automation IDs to install.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    written = install(root, out, set(args.only) if args.only else None)
    print(f"Installed {len(written) // 2} automations to {out}")
    for path in written:
        print(f"- {relpath(root, path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
