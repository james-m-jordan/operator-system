#!/usr/bin/env python3
"""Copy a chat-provided file into a work item and record intake metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, relpath, resolve_root, work_item_dir, write_json


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_metadata(values: list[str]) -> dict[str, str]:
    parsed = {}
    for item in values:
        key, sep, value = item.partition("=")
        if sep:
            parsed[key.strip()] = value.strip()
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--work-item", required=True, help="Work-item ID or path.")
    parser.add_argument("--source-file", required=True, help="Local file captured from chat.")
    parser.add_argument("--source-url", default="", help="Optional source message or file URL.")
    parser.add_argument("--metadata", action="append", default=[], help="Extra key=value metadata.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    source = Path(args.source_file).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise SystemExit(f"source file missing: {source}")

    candidate = Path(args.work_item)
    if not candidate.is_absolute():
        if (root / candidate).exists():
            work_item = root / candidate
        else:
            work_item = work_item_dir(root, config) / args.work_item
    else:
        work_item = candidate
    work_item.mkdir(parents=True, exist_ok=True)
    target_dir = work_item / "source" / "chat-uploads"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        counter = 2
        while target.exists():
            target = target_dir / f"{stem}-{counter}{suffix}"
            counter += 1
    shutil.copy2(source, target)
    metadata = {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "work_item": relpath(root, work_item),
        "stored_path": relpath(root, target),
        "original_path": source.as_posix(),
        "source_url": args.source_url,
        "sha256": sha256(target),
        "bytes": target.stat().st_size,
        "extra": parse_metadata(args.metadata),
    }
    metadata_path = work_item / "metadata" / "chat-file-intake.json"
    existing = []
    if metadata_path.exists():
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    if not isinstance(existing, list):
        existing = [existing]
    existing.append(metadata)
    write_json(metadata_path, existing)
    print(relpath(root, target))
    print(relpath(root, metadata_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
