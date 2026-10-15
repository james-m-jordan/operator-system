#!/usr/bin/env python3
"""Create a run packet for one automation prompt/spec."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import hub_dir, load_config, read_text, relpath, resolve_root, write_json, write_text, run_contract, workspace_lock


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
        "required_checks": automation.get("required_checks", ["output_verified"]),
    }
    text = (
        f"# Automation Run Packet: {automation['title']}\n\n"
        f"- Run ID: `{run_id}`\n"
        f"- Automation ID: `{automation['id']}`\n"
        f"- Created UTC: {metadata['created_utc']}\n"
        f"- Prompt source: `{metadata['prompt_file']}`\n"
        f"- Connectors: {format_list(metadata['connectors'])}\n"
        f"- Expected writes: {format_list(metadata['writes'])}\n"
        f"- Closeout: {metadata['closeout']}\n\n"
        f"{run_contract(run_id)}\n"
        f"Required acceptance checks: {format_list(metadata['required_checks'])}.\n\n"
        "## Prompt\n\n"
        f"{prompt.rstrip()}\n"
    )
    return text, metadata


def invoke_agent(root: Path, config: dict[str, object], run_dir: Path, packet_path: Path) -> int:
    """Run the configured agent command on the packet and record the result."""
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    command = runtime.get("agent_command")
    if isinstance(command, str):
        command = [command]
    if not isinstance(command, list) or not command:
        raise SystemExit(
            "no runtime.agent_command configured in hub/config/org.json; "
            'configure an argv wrapper that consumes packet text on stdin and closes OPERATOR_RUN_ID'
        )
    resolved = [str(part).replace("{packet}", str(packet_path)) for part in command]
    timeout = runtime.get("agent_timeout_seconds") if isinstance(runtime.get("agent_timeout_seconds"), int) else 3600
    started = time.monotonic()
    try:
        env = dict(os.environ, OPERATOR_RUN_ID=run_dir.name, OPERATOR_WORKSPACE=str(root), OPERATOR_PACKET=str(packet_path))
        write_json(run_dir / "started.json", {"started_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        result = subprocess.run(resolved, cwd=root, input=read_text(packet_path), env=env,
                                capture_output=True, text=True, check=False, timeout=timeout)
        returncode, output = result.returncode, (result.stdout + result.stderr)[-4000:]
    except FileNotFoundError:
        returncode, output = 127, f"{resolved[0]} not found"
    except subprocess.TimeoutExpired:
        returncode, output = 124, f"agent command timed out after {timeout}s"
    completed = False
    reason = "agent process failed"
    if returncode == 0:
        from run_close import validate_close, read_chain, chain_path
        try:
            close = json.loads((run_dir / "close.json").read_text())
            meta = json.loads((run_dir / "run.json").read_text())
            validate_close(root, meta, close)
            receipts = read_chain(chain_path(root, config))
            chained = next((e for e in reversed(receipts) if e["run_id"] == meta["run_id"]), None)
            if chained != close:
                raise ValueError("closeout does not match its chained receipt")
            completed = close["outcome"] in {"success", "no_op"}
            reason = "verified completion" if completed else f"run ended {close['outcome']}"
        except (ValueError, OSError, KeyError, TypeError) as exc:
            reason = f"missing or invalid closeout: {exc}"
    runner_exit = returncode if returncode else (0 if completed else 3)
    write_json(
        run_dir / "invoke.json",
        {
            "invoked_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "command": resolved,
            "returncode": returncode,
            "runner_exit": runner_exit,
            "completed": completed,
            "completion_detail": reason,
            "duration_seconds": round(time.monotonic() - started, 1),
            "output_tail": output,
        },
    )
    print(f"Agent invocation exited {returncode}; see {relpath(root, run_dir / 'invoke.json')}")
    print(reason)
    return runner_exit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--automation-id", required=True, help="Automation ID from the manifest.")
    parser.add_argument("--print-prompt", action="store_true", help="Print run packet instead of writing it.")
    parser.add_argument("--invoke", action="store_true", help="Run the configured runtime.agent_command on the packet after writing it.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    manifest = load_manifest(root, config)
    automation = find_automation(manifest, args.automation_id)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + args.automation_id + "-" + uuid.uuid4().hex[:8]
    packet_text, metadata = build_run_packet(root, config, automation, run_id)
    if args.print_prompt:
        print(packet_text, end="")
        return 0

    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    run_root = root / str(runtime.get("run_root", "hub/MEMORY/automation-runs"))
    run_dir = run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    write_text(run_dir / "run.md", packet_text)
    write_json(run_dir / "run.json", metadata)
    print(relpath(root, run_dir / "run.md"))
    if args.invoke:
        with workspace_lock(root, config, name="automation-" + str(automation["id"])):
            return invoke_agent(root, config, run_dir, run_dir / "run.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
