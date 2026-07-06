#!/usr/bin/env python3
"""Record the outcome and improvement of one automation run.

Every close is also appended to a tamper-evident hash chain at
hub/MEMORY/indexes/close-chain.jsonl; verify it with --verify-chain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, memory_dir, relpath, resolve_root, workspace_lock, write_json

OUTCOMES = ["success", "partial", "failure"]
IMPROVEMENTS = ["lesson", "correction", "pruning", "promotion", "none"]
GENESIS_HASH = "0" * 64


def chain_path(root: Path, config: dict[str, object]) -> Path:
    return memory_dir(root, config) / "indexes" / "close-chain.jsonl"


def entry_hash(entry: dict[str, object], prev_hash: str) -> str:
    body = {key: value for key, value in entry.items() if key != "hash"}
    return hashlib.sha256((prev_hash + json.dumps(body, sort_keys=True)).encode("utf-8")).hexdigest()


def append_chain(root: Path, config: dict[str, object], close: dict[str, object]) -> dict[str, object]:
    path = chain_path(root, config)
    with workspace_lock(root, config, name="close-chain"):
        prev_hash = GENESIS_HASH
        if path.exists():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if lines:
                prev_hash = json.loads(lines[-1]).get("hash", GENESIS_HASH)
        entry = {
            "run_id": close["run_id"],
            "automation_id": close["automation_id"],
            "closed_utc": close["closed_utc"],
            "outcome": close["outcome"],
            "improvement": close["improvement"],
            "prev_hash": prev_hash,
        }
        entry["hash"] = entry_hash(entry, prev_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def verify_chain(root: Path, config: dict[str, object]) -> int:
    path = chain_path(root, config)
    if not path.exists():
        print("No close chain yet; nothing to verify.")
        return 0
    prev_hash = GENESIS_HASH
    number = 0
    for number, line in enumerate((line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()), start=1):
        entry = json.loads(line)
        if entry.get("prev_hash") != prev_hash:
            print(f"BROKEN at entry {number} ({entry.get('run_id')}): prev_hash mismatch")
            return 1
        if entry.get("hash") != entry_hash(entry, prev_hash):
            print(f"BROKEN at entry {number} ({entry.get('run_id')}): record hash mismatch")
            return 1
        prev_hash = entry["hash"]
    print(f"Chain OK: {number} close records verified ({relpath(root, path)})")
    return 0


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
    parser.add_argument("--outcome", default="", choices=OUTCOMES + [""], help="Run outcome (required unless --verify-chain).")
    parser.add_argument("--verify-chain", action="store_true", help="Verify the close-chain ledger and exit.")
    parser.add_argument("--improvement", default="none", choices=IMPROVEMENTS, help="Improvement left by this run.")
    parser.add_argument("--improvement-ref", default="", help="Path or short pointer to the improvement.")
    parser.add_argument("--lesson", default="", help="Lesson text to add or re-confirm in LESSONS.md; implies --improvement lesson.")
    parser.add_argument("--note", default="", help="Optional closeout note.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    if args.verify_chain:
        return verify_chain(root, config)
    if not args.outcome:
        raise SystemExit("--outcome is required")
    run_dir = find_run_dir(run_root_dir(root, config), args.run_id, args.latest)

    if args.lesson:
        from lesson_add import add_lesson

        summary = add_lesson(root, config, args.lesson, args.improvement_ref or "hub/MEMORY/agent-action-log.md")
        print(summary)
        args.improvement = "lesson"
        args.improvement_ref = "hub/MEMORY/LESSONS.md"

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
    chain_entry = append_chain(root, config, close)
    close["prev_hash"] = chain_entry["prev_hash"]
    close["hash"] = chain_entry["hash"]
    write_json(run_dir / "close.json", close)
    print(relpath(root, run_dir / "close.json"))
    if args.improvement == "none":
        print("Warning: run closed without an improvement; the ratchet expects one lesson, correction, or pruning per substantive run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
