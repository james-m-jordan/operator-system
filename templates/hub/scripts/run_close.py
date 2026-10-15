#!/usr/bin/env python3
"""Close a run once with evidence; explicit amendments append to the receipt chain."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from operator_common import load_config, memory_dir, relpath, resolve_root, workspace_lock, write_json

OUTCOMES = ["success", "no_op", "partial", "blocked", "failure"]
IMPROVEMENTS = ["lesson", "correction", "pruning", "promotion", "none"]
GENESIS_HASH = "0" * 64


def chain_path(root: Path, config: dict[str, object]) -> Path:
    return memory_dir(root, config) / "indexes/close-chain.jsonl"


def entry_hash(entry: dict[str, object], prev_hash: str) -> str:
    body = {key: value for key, value in entry.items() if key != "hash"}
    return hashlib.sha256((prev_hash + json.dumps(body, sort_keys=True)).encode()).hexdigest()


def read_chain(path: Path) -> list[dict[str, object]]:
    entries = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    previous = GENESIS_HASH
    for number, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ValueError(f"BROKEN at entry {number}: expected an object")
        if entry.get("prev_hash") != previous or entry.get("hash") != entry_hash(entry, previous):
            raise ValueError(f"BROKEN at entry {number} ({entry.get('run_id')}): record hash mismatch")
        previous = entry["hash"]
    return entries


def verify_chain(root: Path, config: dict[str, object]) -> int:
    try:
        entries = read_chain(chain_path(root, config))
        latest = {entry["run_id"]: entry for entry in entries}
        for run_id, entry in latest.items():
            path = run_root_dir(root, config) / run_id / "close.json"
            # Retained/archived runs need not have a live materialized close file.
            if entry.get("format") == 2 and path.exists() and json.loads(path.read_text()) != entry:
                raise ValueError(f"BROKEN close.json for {run_id}: differs from chained receipt")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"BROKEN: {exc}")
        return 1
    print(f"Chain OK: {len(entries)} close records verified ({relpath(root, chain_path(root, config))})")
    return 0


def run_root_dir(root: Path, config: dict[str, object]) -> Path:
    return root / str(config.get("runtime", {}).get("run_root", "hub/MEMORY/automation-runs"))


def find_run_dir(run_root: Path, run_id: str, latest: bool) -> Path:
    if run_id:
        if Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ValueError("run ID must be a single directory name")
        result = run_root / run_id
        if not (result / "run.json").exists():
            raise ValueError(f"no run packet found for run id: {run_id}")
        return result
    if latest:
        candidates = sorted(p.parent for p in run_root.glob("*/run.json"))
        unclosed = [p for p in candidates if not (p / "close.json").exists()]
        if len(unclosed) > 1:
            raise ValueError("multiple open runs; use --run-id to avoid closing another worker's run")
        if unclosed:
            return unclosed[0]
        if candidates:
            return candidates[-1]
    raise ValueError("pass --run-id for an existing run")


def validate_close(root: Path, meta: dict, close: dict) -> None:
    if not isinstance(close, dict) or not isinstance(meta, dict):
        raise ValueError("run and close records must be objects")
    if close.get("run_id") != meta.get("run_id") or close.get("automation_id") != meta.get("automation_id"):
        raise ValueError("close record does not belong to this run")
    if close.get("outcome") not in OUTCOMES:
        raise ValueError("invalid outcome")
    if close["outcome"] in {"success", "no_op"}:
        checks = close.get("checks", {})
        required = meta.get("required_checks") or ["output_verified"]
        if not isinstance(required, list) or not all(isinstance(name, str) and name for name in required):
            raise ValueError("required_checks must be a list of names")
        if not isinstance(checks, dict) or not checks or any(value is not True for value in checks.values()) or any(checks.get(name) is not True for name in required):
            raise ValueError("success/no_op requires passing acceptance checks: " + ", ".join(required))
        evidence = close.get("evidence", [])
        if not isinstance(evidence, list) or not evidence or not all(isinstance(value, str) and value for value in evidence):
            raise ValueError("success/no_op requires --evidence for outputs or source coverage")
        for value in evidence:
            url = urlparse(value)
            if url.scheme in {"https", "http"} and url.netloc:
                continue  # The caller supplies the verified permalink; no external access here.
            path = (root / value).resolve()
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"evidence must be a nonempty file or verified HTTP(S) URL: {value}")
    elif not str(close.get("note", "")).strip():
        raise ValueError("partial/blocked/failure requires --note describing the blocker and next action")


def close_run(root: Path, config: dict, run_dir: Path, values: dict, amend: bool = False) -> dict:
    meta = json.loads((run_dir / "run.json").read_text())
    values = {"run_id": meta["run_id"], "automation_id": meta["automation_id"], **values}
    validate_close(root, meta, values)
    path = chain_path(root, config)
    with workspace_lock(root, config, name="close-chain"):
        entries = read_chain(path)
        previous_close = next((e for e in reversed(entries) if e["run_id"] == meta["run_id"]), None)
        close_path = run_dir / "close.json"
        if previous_close:
            if all(previous_close.get(key) == value for key, value in values.items()):
                write_json(close_path, previous_close)  # Repair a crash after the chain commit.
                return previous_close
            if not amend:
                raise ValueError("run already closed differently; use --amend --note with the reason")
            if not values.get("note"):
                raise ValueError("an amendment requires --note explaining the correction")
        elif close_path.exists():
            raise ValueError("close.json has no matching chain entry; reconcile before closing")
        elif amend:
            raise ValueError("cannot amend a run that has not been closed")
        if values.get("lesson"):
            from lesson_add import add_lesson
            add_lesson(root, config, values["lesson"], values.get("improvement_ref") or values["evidence"][0])
        entry = {**values, "format": 2, "revision": int((previous_close or {}).get("revision", 1 if previous_close else 0)) + 1,
                 "closed_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "prev_hash": entries[-1]["hash"] if entries else GENESIS_HASH}
        entry["hash"] = entry_hash(entry, entry["prev_hash"])
        # Atomically replace the chain so a killed writer cannot leave a partial line.
        from operator_common import write_text
        write_text(path, "".join(json.dumps(e, sort_keys=True) + "\n" for e in [*entries, entry]))
        write_json(close_path, entry)
        return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--latest", action="store_true", help="Interactive compatibility only; refuses multiple open runs.")
    parser.add_argument("--outcome", default="", choices=OUTCOMES + [""])
    parser.add_argument("--verify-chain", action="store_true")
    parser.add_argument("--amend", action="store_true")
    parser.add_argument("--improvement", default="none", choices=IMPROVEMENTS)
    parser.add_argument("--improvement-ref", default="")
    parser.add_argument("--lesson", default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--check", action="append", default=[], help="Acceptance result as name=pass or name=fail.")
    args = parser.parse_args()
    root = resolve_root(args.root)
    config = load_config(root)
    if args.verify_chain:
        return verify_chain(root, config)
    try:
        checks = {}
        for value in args.check:
            name, sep, result = value.partition("=")
            if not sep or not name or result not in {"pass", "fail"} or name in checks:
                raise ValueError("checks must be unique name=pass or name=fail values")
            checks[name] = result == "pass"
        run_dir = find_run_dir(run_root_dir(root, config), args.run_id, args.latest)
        if args.lesson and not (args.improvement_ref or args.evidence):
            raise ValueError("a lesson requires an evidence reference")
        close_run(root, config, run_dir, {"outcome": args.outcome, "checks": checks, "evidence": args.evidence,
                  "improvement": "lesson" if args.lesson else args.improvement,
                  "improvement_ref": args.improvement_ref, "lesson": args.lesson, "note": args.note}, args.amend)
    except (ValueError, OSError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(relpath(root, run_dir / "close.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
