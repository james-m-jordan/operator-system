#!/usr/bin/env python3
"""Single entry point for the operator-system helper scripts.

Commands:
  startup            config check + preflight + sync (dry) + index + digest + health
  doctor             read-only health review: config check, health --strict, compact plan
  run <id>           create a run packet (add --invoke to execute the agent command)
  close ...          record a run outcome (args pass through to run_close.py)
  search <terms...>  ranked search across memory, wiki, and knowledge base
  review             create a system-review-loop packet (add --invoke to execute)
  compact            action-log rotation plan (add --execute to rotate)
  sweep              retention sweep plan (add --execute to retire old artifacts)
  wiki               recompile hub/wiki/overview.md
  report             compile the executive operator report (add --write to save)
  pack export|import lesson pack export/import (args pass through to lesson_pack.py)
  verify             verify the tamper-evident close chain
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(script: str, *args: str) -> int:
    result = subprocess.run([sys.executable, str(SCRIPT_DIR / script), *args], check=False)
    return result.returncode


def run_chain(steps: list[tuple[str, list[str]]]) -> int:
    for script, args in steps:
        print(f"==> {script} {' '.join(args)}".rstrip())
        returncode = run_script(script, *args)
        if returncode != 0:
            print(f"ops: {script} exited {returncode}; stopping.")
            return returncode
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(__doc__.strip())
        return 0
    command, rest = argv[0], argv[1:]
    root_args = ["--root", "."]

    if command == "startup":
        return run_chain(
            [
                ("config_check.py", root_args),
                ("preflight_capabilities.py", root_args),
                ("sync_workspace.py", root_args),
                ("memory_index_refresh.py", root_args + ["--write", "--validate"]),
                ("state_digest.py", root_args),
                ("memory_health.py", root_args + ["--write"]),
            ]
        )
    if command == "doctor":
        return run_chain(
            [
                ("config_check.py", root_args),
                ("memory_health.py", root_args + ["--strict"]),
                ("memory_compact.py", root_args),
                ("retention_sweep.py", root_args),
            ]
        )
    if command == "run":
        if not rest:
            print("usage: ops run <automation-id> [--invoke]")
            return 2
        return run_script("run_automation.py", *root_args, "--automation-id", rest[0], *rest[1:])
    if command == "review":
        return run_script("run_automation.py", *root_args, "--automation-id", "system-review-loop", *rest)
    if command == "close":
        return run_script("run_close.py", *root_args, *rest)
    if command == "search":
        if not rest:
            print("usage: ops search <terms...>")
            return 2
        return run_script("memory_search.py", *root_args, "--query", " ".join(rest))
    if command == "compact":
        return run_script("memory_compact.py", *root_args, *rest)
    if command == "sweep":
        return run_script("retention_sweep.py", *root_args, *rest)
    if command == "wiki":
        return run_script("wiki_compile.py", *root_args, *rest)
    if command == "report":
        return run_script("operator_report.py", *root_args, *rest)
    if command == "pack":
        if not rest or rest[0] not in {"export", "import"}:
            print("usage: ops pack export|import [args...]")
            return 2
        return run_script("lesson_pack.py", rest[0], *root_args, *rest[1:])
    if command == "verify":
        return run_script("run_close.py", *root_args, "--verify-chain")
    print(f"unknown command: {command}")
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
