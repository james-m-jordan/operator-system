#!/usr/bin/env python3
"""Scaffold an organization-neutral operator-system workspace."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "templates"


REQUIRED_CONFIG_KEYS = {
    "org_name",
    "workspace_name",
    "admin_name",
    "timezone",
    "primary_status_channel",
    "intake_channel",
    "work_item_root",
    "knowledge_base_root",
    "hub_root",
}


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    missing = sorted(REQUIRED_CONFIG_KEYS - set(config))
    if missing:
        raise ValueError(f"Config missing required keys: {', '.join(missing)}")
    return config


def token_map(config: dict[str, Any]) -> dict[str, str]:
    return {
        "{{ORG_NAME}}": str(config["org_name"]),
        "{{WORKSPACE_NAME}}": str(config["workspace_name"]),
        "{{ADMIN_NAME}}": str(config["admin_name"]),
        "{{TIMEZONE}}": str(config["timezone"]),
        "{{PRIMARY_STATUS_CHANNEL}}": str(config["primary_status_channel"]),
        "{{INTAKE_CHANNEL}}": str(config["intake_channel"]),
        "{{DATE}}": date.today().isoformat(),
    }


def render_text(text: str, tokens: dict[str, str]) -> str:
    for token, value in tokens.items():
        text = text.replace(token, value)
    return text


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_templates(destination: Path, tokens: dict[str, str]) -> None:
    for source in TEMPLATE_ROOT.rglob("*"):
        if source.is_dir():
            continue
        if "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        relative = source.relative_to(TEMPLATE_ROOT)
        target = destination / relative
        text = source.read_text(encoding="utf-8")
        write_text(target, render_text(text, tokens))


def write_generated_files(destination: Path, config: dict[str, Any], tokens: dict[str, str]) -> None:
    hub_root = destination / str(config["hub_root"])
    memory_root = hub_root / "MEMORY"
    knowledge_root = destination / str(config["knowledge_base_root"])
    work_item_root = destination / str(config["work_item_root"])

    write_text(
        destination / ".gitignore",
        "\n".join(
            [
                ".DS_Store",
                "__pycache__/",
                ".pytest_cache/",
                "local-private/",
                "*.log",
                "",
            ]
        ),
    )

    org_config = dict(config)
    org_config["generated_from"] = "operator-system-starter"
    write_text(hub_root / "config" / "org.json", json.dumps(org_config, indent=2) + "\n")

    capabilities = {
        "generated": tokens["{{DATE}}"],
        "checks": {
            "chat": {"ok": False, "connector": config.get("connectors", {}).get("chat")},
            "email": {"ok": False, "connector": config.get("connectors", {}).get("email")},
            "calendar": {"ok": False, "connector": config.get("connectors", {}).get("calendar")},
            "tasks": {"ok": False, "connector": config.get("connectors", {}).get("tasks")},
            "git_push_path": {"ok": False, "note": "Run local preflight after configuring credentials."},
        },
        "required_down": ["chat", "email", "calendar", "tasks", "git_push_path"],
    }
    write_text(memory_root / "capabilities.json", json.dumps(capabilities, indent=2) + "\n")

    write_text(
        memory_root / "state-digest.md",
        render_text(
            """# State Digest

- Generated: {{DATE}} by scaffold.
- Organization: {{ORG_NAME}}
- Workspace: {{WORKSPACE_NAME}}
- Capability summary: all connectors pending local preflight.

## Current Work

- No active work items indexed yet.

## Next Actions

1. Configure connectors and credentials.
2. Add real team members to `hub/admin-docs/team.md`.
3. Create the first canonical work item under `work-items/`.
4. Install or port preflight, sync, and state-digest scripts.
""",
            tokens,
        ),
    )

    for relative, title in [
        ("people-bios.md", "People Bios"),
        ("work-item-bios.md", "Work Item Bios"),
        ("comms.md", "Communication Memory"),
        ("references.md", "Reference Memory"),
        ("repo-syncs/README.md", "Repo Sync Reports"),
        ("archive/README.md", "Memory Archive"),
        ("../wiki/README.md", "Wiki"),
    ]:
        write_text(
            memory_root / relative,
            f"# {title}\n\nInitial scaffold for {config['org_name']}.\n",
        )

    write_text(
        hub_root / "scripts" / "README.md",
        """# Scripts

Generated helper scripts:

- `preflight_capabilities.py` - writes `hub/MEMORY/capabilities.json`.
- `sync_workspace.py` - fetches nested git repos and writes a sync report.
- `memory_index_refresh.py` - indexes `work-items/` and blockers.
- `state_digest.py` - regenerates `hub/MEMORY/state-digest.md`.
- `memory_health.py` - measures compact memory surfaces against `memory_budgets`.
- `memory_compact.py` - rotates old action-log entries into `hub/MEMORY/archive/` (dry-run by default).
- `package_gate.py` - checks whether one work item has source, metadata, and context.
- `install_automations.py` - installs automation prompt/spec bundles from `hub/automations/automation-manifest.json`.
- `task_draft.py` - writes no-terminal collaborator task drafts under `hub/MEMORY/task-drafts/`.
- `backup_verify.py` - verifies source and optional destination backup paths.
- `backup_transfer.py` - writes a dry-run backup transfer plan or explicitly executes local-copy/rsync transfer.
- `chat_file_fetch.py` - fetches chat-hosted files into ignored local-private storage.
- `chat_file_intake.py` - copies a captured chat file into a work item and records metadata.
- `run_automation.py` - creates a dated run packet from one automation prompt/spec.
- `publish_status.py` - writes configured publisher outbox payloads without sending external messages.
- `deliver_outbox.py` - dry-runs or executes configured outbox delivery adapters.
- `export_runtime_adapters.py` - exports cron and GitHub Actions scheduler drafts plus publisher notes.

Recommended startup refresh:

```bash
python3 hub/scripts/preflight_capabilities.py --root .
python3 hub/scripts/sync_workspace.py --root .
python3 hub/scripts/memory_index_refresh.py --root . --write --validate
python3 hub/scripts/state_digest.py --root .
python3 hub/scripts/memory_health.py --root . --write
```

Install automation prompt/spec bundles:

```bash
python3 hub/scripts/install_automations.py --root . --out .operator-automations
```

Export runtime adapter drafts and create a local run packet:

```bash
python3 hub/scripts/export_runtime_adapters.py --root .
python3 hub/scripts/run_automation.py --root . --automation-id morning-control-panel
python3 hub/scripts/publish_status.py --root . --publisher status --message "Status text here"
python3 hub/scripts/deliver_outbox.py --root . --publisher status --latest
python3 hub/scripts/backup_transfer.py --root . --write-report
printf 'example upload\n' > /tmp/operator-upload.txt
python3 hub/scripts/chat_file_fetch.py --root . --provider direct-url --url file:///tmp/operator-upload.txt
```
""",
    )

    write_text(
        knowledge_root / "README.md",
        f"# Knowledge Base\n\nShared standards, procedures, examples, and references for {config['org_name']}.\n",
    )
    work_item_root.mkdir(parents=True, exist_ok=True)
    (destination / "local-private").mkdir(parents=True, exist_ok=True)


def scaffold(config: dict[str, Any], destination: Path, force: bool = False) -> None:
    if destination.exists():
        if not force and any(destination.iterdir()):
            raise FileExistsError(f"Destination exists and is not empty: {destination}")
        if force:
            shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    tokens = token_map(config)
    copy_templates(destination, tokens)
    write_generated_files(destination, config, tokens)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Path to org config JSON.")
    parser.add_argument("--out", type=Path, required=True, help="Destination workspace path.")
    parser.add_argument("--force", action="store_true", help="Replace destination if it exists.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = load_config(args.config)
    scaffold(config, args.out, force=args.force)
    print(f"Scaffolded operator workspace at {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
