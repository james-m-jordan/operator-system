#!/usr/bin/env python3
"""Scaffold a demo workspace and drive the full operator loop end to end.

Shows the whole system working in under a minute: scaffold, startup chain,
an automation run executed by a stand-in agent command, lesson recording,
run closeout, wiki synthesis, and the health trend.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]


def step(title: str, command: list[str], cwd: Path) -> None:
    print(f"\n=== {title}")
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(f"demo step failed ({result.returncode}): {title}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="Workspace path. Defaults to a fresh temp directory.")
    args = parser.parse_args()

    out = args.out or Path(tempfile.mkdtemp(prefix="operator-demo-")) / "workspace"
    python = sys.executable

    step(
        "Scaffold a workspace from the example config",
        [python, str(KIT_ROOT / "scripts" / "scaffold_workspace.py"), "--config", str(KIT_ROOT / "config" / "org.example.json"), "--out", str(out), "--force"],
        KIT_ROOT,
    )
    step("Startup chain (config check, preflight, sync, index, digest, health)", [python, "hub/scripts/ops.py", "startup"], out)
    step("Create a run packet and execute it with the configured agent command", [python, "hub/scripts/ops.py", "run", "morning-control-panel", "--invoke"], out)
    step(
        "Close the run, recording a lesson (deduped with hit counts)",
        [python, "hub/scripts/ops.py", "close", "--latest", "--outcome", "success", "--lesson", "Demo: verify connector health before scheduled sends."],
        out,
    )
    step("Compile the synthesis wiki", [python, "hub/scripts/ops.py", "wiki"], out)
    step("Refresh health so the trend records this run", [python, "hub/scripts/memory_health.py", "--root", ".", "--write"], out)
    step("Search memory for the lesson we just recorded", [python, "hub/scripts/ops.py", "search", "connector", "health"], out)
    step("Doctor: strict health gate + rotation and retention plans", [python, "hub/scripts/ops.py", "doctor"], out)

    print("\n=== Demo complete")
    print(f"Workspace: {out}")
    print("Look at: hub/MEMORY/state-digest.md, hub/MEMORY/LESSONS.md, hub/wiki/overview.md,")
    print("hub/MEMORY/automation-runs/ (run.md, close.json, invoke.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
