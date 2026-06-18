#!/usr/bin/env python3
"""Write a status message into a configured publisher outbox."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, read_text, relpath, resolve_root, write_json, write_text


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower() or "publisher"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--publisher", default="status", help="Publisher key from runtime.publisher_targets.")
    parser.add_argument("--message", default="", help="Message text.")
    parser.add_argument("--message-file", default="", help="Path to message text.")
    parser.add_argument("--title", default="Operator status update", help="Outbox item title.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    publishers = runtime.get("publisher_targets", {}) if isinstance(runtime.get("publisher_targets"), dict) else {}
    publisher = publishers.get(args.publisher, {"type": "markdown-outbox"})
    if not isinstance(publisher, dict):
        publisher = {"type": str(publisher)}
    message = args.message
    if args.message_file:
        message_path = Path(args.message_file)
        if not message_path.is_absolute():
            message_path = root / message_path
        message = read_text(message_path)
    if not message.strip():
        raise SystemExit("message or message-file is required")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outbox_root = root / str(runtime.get("outbox_root", "hub/MEMORY/outbox"))
    outbox_dir = outbox_root / slugify(args.publisher)
    outbox_dir.mkdir(parents=True, exist_ok=True)
    base = outbox_dir / f"{timestamp}-{slugify(args.title)}"
    payload = {
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "publisher": args.publisher,
        "publisher_config": publisher,
        "title": args.title,
        "message": message.strip(),
    }
    write_json(base.with_suffix(".json"), payload)
    write_text(
        base.with_suffix(".md"),
        f"# {args.title}\n\n"
        f"- Publisher: `{args.publisher}`\n"
        f"- Target type: `{publisher.get('type', 'markdown-outbox')}`\n"
        f"- Target: `{publisher.get('channel') or publisher.get('destination') or 'outbox'}`\n"
        f"- Created UTC: {payload['created_utc']}\n\n"
        f"## Message\n\n{message.strip()}\n",
    )
    print(relpath(root, base.with_suffix(".md")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
