#!/usr/bin/env python3
"""Write a generic tool and connector capability snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, memory_dir, resolve_root, write_json


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]} timed out after {timeout}s"


def check_command(name: str, command: str | None = None) -> dict[str, object]:
    executable = command or name
    path = shutil.which(executable)
    if not path:
        return {"ok": False, "detail": f"{executable} not found"}
    return {"ok": True, "path": path}


def check_python() -> dict[str, object]:
    return {
        "ok": True,
        "version": ".".join(str(part) for part in sys.version_info[:3]),
        "path": sys.executable,
    }


def check_git() -> dict[str, object]:
    if shutil.which("git") is None:
        return {"ok": False, "detail": "git not found"}
    rc, out, err = run(["git", "--version"])
    return {"ok": rc == 0, "version": out, "detail": err} if rc else {"ok": True, "version": out}


def check_github_cli() -> dict[str, object]:
    if shutil.which("gh") is None:
        return {"ok": False, "detail": "gh not found"}
    rc, out, err = run(["gh", "auth", "status"])
    return {"ok": rc == 0, "detail": out or err}


def build_snapshot(root: Path, config: dict[str, object]) -> dict[str, object]:
    connectors = config.get("connectors", {})
    if not isinstance(connectors, dict):
        connectors = {}

    checks: dict[str, object] = {
        "python": check_python(),
        "git": check_git(),
    }
    if connectors.get("tasks") == "github":
        checks["github_cli"] = check_github_cli()

    for item in config.get("optional_commands", []) or []:
        if isinstance(item, str):
            checks[item] = check_command(item)

    connector_checks = {}
    for name, provider in connectors.items():
        connector_checks[name] = {
            "ok": False,
            "provider": provider,
            "detail": "Connector health must be verified by the runtime that owns this connector.",
        }
    checks["connectors"] = connector_checks

    required = set(config.get("required_capabilities") or ["git", "python"])
    degraded = [name for name, result in checks.items() if isinstance(result, dict) and not result.get("ok", False)]
    required_down = [name for name in degraded if name in required]

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "workspace": root.as_posix(),
        "checks": checks,
        "degraded": degraded,
        "required_down": required_down,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root. Defaults to the generated workspace root.")
    parser.add_argument("--json", action="store_true", help="Also print JSON to stdout.")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if required capabilities are down.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    snapshot = build_snapshot(root, config)
    out_path = memory_dir(root, config) / "capabilities.json"
    write_json(out_path, snapshot)

    print(f"Wrote {out_path.relative_to(root)}")
    for name, result in snapshot["checks"].items():
        if name == "connectors":
            continue
        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        print(f"- {name}: {'ok' if ok else 'DOWN'}")
    if snapshot["required_down"]:
        print("Required capabilities down: " + ", ".join(snapshot["required_down"]))
    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 1 if args.strict and snapshot["required_down"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
