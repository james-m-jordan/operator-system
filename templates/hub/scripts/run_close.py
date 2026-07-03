#!/usr/bin/env python3
"""Record the outcome and improvement of one automation run."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, relpath, resolve_root, write_json

OUTCOMES = ["success", "partial", "failure"]
IMPROVEMENTS = ["lesson", "correction", "pruning", "promotion", "none"]


def run_root_dir(root: Path, config: dict[str, object]) -> Path:
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    return root / str(runtime.get("run_root", "hub/MEMORY/automation-runs"))


def find_run_dir(run_root: Path, run_id: str, latest: bool) -> Path:
    if run_id:
        run_dir = run_root / run_id
        if not (run_dir / "run.json").exists():
            raise SystemExit(f"no run packet found for run id: {run_id}")
        return run_dir
    if latest:
        candidates = sorted(child for child in run_root.iterdir() if (child / "run.json").exists()) if run_root.exists() else []
        if not candidates:
            raise SystemExit(f"no run packets found under {run_root}")
        return candidates[-1]
    raise SystemExit("pass --run-id or --latest")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--run-id", default="", help="Run ID to close.")
    parser.add_argument("--latest", action="store_true", help="Close the most recent run packet.")
    parser.add_argument("--outcome", required=True, choices=OUTCOMES, help="Run outcome.")
    parser.add_argument("--improvement", default="none", choices=IMPROVEMENTS, help="Improvement left by this run.")
    parser.add_argument("--improvement-ref", default="", help="Path or short pointer to the improvement.")
    parser.add_argument("--note", default="", help="Optional closeout note.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    run_dir = find_run_dir(run_root_dir(root, config), args.run_id, args.latest)

    run_meta = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    close = {
        "run_id": run_meta.get("run_id", run_dir.name),
        "automation_id": run_meta.get("automation_id", ""),
        "closed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "outcome": args.outcome,
        "improvement": args.improvement,
        "improvement_ref": args.improvement_ref,
        "note": args.note,
    }
    write_json(run_dir / "close.json", close)
    print(relpath(root, run_dir / "close.json"))
    if args.improvement == "none":
        print("Warning: run closed without an improvement; the ratchet expects one lesson, correction, or pruning per substantive run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
