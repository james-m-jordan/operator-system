#!/usr/bin/env python3
"""Dry-run or execute delivery for one configured publisher outbox item."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, memory_dir, relpath, resolve_root, write_json, write_text


def slugify(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value)).strip("-").lower() or "outbox"


def runtime_config(config: dict[str, object]) -> dict[str, object]:
    return config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}


def outbox_root(root: Path, config: dict[str, object]) -> Path:
    runtime = runtime_config(config)
    return root / str(runtime.get("outbox_root", "hub/MEMORY/outbox"))


def latest_outbox_path(root: Path, config: dict[str, object], publisher: str) -> Path:
    candidates = sorted((outbox_root(root, config) / slugify(publisher)).glob("*.json"))
    if not candidates:
        raise SystemExit(f"no outbox items found for publisher: {publisher}")
    return candidates[-1]


def load_payload(root: Path, config: dict[str, object], args: argparse.Namespace) -> tuple[Path, dict[str, object]]:
    if args.outbox_item:
        path = Path(args.outbox_item)
        if not path.is_absolute():
            path = root / path
    else:
        path = latest_outbox_path(root, config, args.publisher)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"outbox item is not a JSON object: {relpath(root, path)}")
    return path, payload


def configured_delivery(payload: dict[str, object]) -> dict[str, object]:
    publisher_config = payload.get("publisher_config", {})
    if not isinstance(publisher_config, dict):
        return {"type": str(publisher_config)}
    delivery = publisher_config.get("delivery", {})
    if isinstance(delivery, dict):
        return dict(delivery)
    return dict(publisher_config)


def delivery_type(payload: dict[str, object], delivery: dict[str, object]) -> str:
    publisher_config = payload.get("publisher_config", {})
    fallback = "markdown-outbox"
    if isinstance(publisher_config, dict):
        fallback = str(publisher_config.get("type", fallback))
    return str(delivery.get("type", fallback))


def env_or_value(config: dict[str, object], value_key: str, env_key: str) -> str:
    value = config.get(value_key, "")
    if value:
        return str(value)
    env_name = config.get(env_key, "")
    return os.environ.get(str(env_name), "") if env_name else ""


def webhook_payload(adapter: str, payload: dict[str, object]) -> dict[str, object]:
    if adapter == "slack-webhook":
        return {"text": str(payload.get("message", ""))}
    return {
        "publisher": payload.get("publisher"),
        "title": payload.get("title"),
        "message": payload.get("message"),
        "created_utc": payload.get("created_utc"),
    }


def deliver_webhook(adapter: str, delivery: dict[str, object], payload: dict[str, object], execute: bool) -> tuple[int, str]:
    url = env_or_value(delivery, "url", "url_env")
    if not url:
        detail = "missing webhook url; set url or url_env"
        return (2 if execute else 0), detail
    if not execute:
        return 0, f"dry-run webhook delivery to {delivery.get('url_env') or url}"
    data = json.dumps(webhook_payload(adapter, payload)).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            return 0, f"webhook status={response.status} body={body[:500]}"
    except urllib.error.URLError as exc:
        return 2, f"webhook failed: {exc}"


def deliver_command(delivery: dict[str, object], payload: dict[str, object], execute: bool) -> tuple[int, str]:
    command = delivery.get("command", [])
    if isinstance(command, str):
        command = shlex.split(command)
    if not isinstance(command, list) or not command:
        detail = "missing command"
        return (2 if execute else 0), detail
    command = [str(part) for part in command]
    if not execute:
        return 0, "dry-run command: " + shlex.join(command)
    env = dict(os.environ)
    env.update(
        {
            "OPERATOR_PUBLISHER": str(payload.get("publisher", "")),
            "OPERATOR_TITLE": str(payload.get("title", "")),
            "OPERATOR_MESSAGE": str(payload.get("message", "")),
        }
    )
    result = subprocess.run(
        command,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    detail = (result.stdout + result.stderr).strip()
    return result.returncode, detail[:1000]


def deliver_github_issue(delivery: dict[str, object], payload: dict[str, object], execute: bool) -> tuple[int, str]:
    repo = env_or_value(delivery, "repo", "repo_env")
    if not repo:
        detail = "missing GitHub repo; set repo or repo_env"
        return (2 if execute else 0), detail
    command = [
        "gh",
        "issue",
        "create",
        "--repo",
        repo,
        "--title",
        str(payload.get("title", "Operator status update")),
        "--body",
        str(payload.get("message", "")),
    ]
    labels = delivery.get("labels", [])
    if isinstance(labels, str):
        labels = [labels]
    if isinstance(labels, list):
        for label in labels:
            command.extend(["--label", str(label)])
    if not execute:
        return 0, "dry-run GitHub issue command: " + shlex.join(command)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    detail = (result.stdout + result.stderr).strip()
    return result.returncode, detail[:1000]


def deliver(payload: dict[str, object], delivery: dict[str, object], execute: bool) -> tuple[int, str]:
    adapter = delivery_type(payload, delivery)
    if adapter in {"markdown-outbox", "task-draft", "noop"}:
        return 0, f"{adapter} is outbox-only; no external delivery attempted"
    if adapter in {"webhook-json", "slack-webhook"}:
        return deliver_webhook(adapter, delivery, payload, execute)
    if adapter == "command":
        return deliver_command(delivery, payload, execute)
    if adapter == "github-issue":
        return deliver_github_issue(delivery, payload, execute)
    detail = f"unsupported delivery type: {adapter}"
    return (2 if execute else 0), detail


def write_receipt(
    root: Path,
    config: dict[str, object],
    outbox_path: Path,
    payload: dict[str, object],
    delivery: dict[str, object],
    execute: bool,
    returncode: int,
    detail: str,
) -> Path:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    publisher = slugify(payload.get("publisher", "publisher"))
    title = slugify(payload.get("title", "delivery"))
    base = memory_dir(root, config) / "outbox-deliveries" / publisher / f"{timestamp}-{title}"
    receipt = {
        "created_utc": created,
        "outbox_item": relpath(root, outbox_path),
        "publisher": payload.get("publisher"),
        "delivery": delivery,
        "executed": execute,
        "returncode": returncode,
        "detail": detail,
    }
    write_json(base.with_suffix(".json"), receipt)
    write_text(
        base.with_suffix(".md"),
        f"# Outbox Delivery Receipt\n\n"
        f"- Publisher: `{payload.get('publisher')}`\n"
        f"- Outbox item: `{relpath(root, outbox_path)}`\n"
        f"- Delivery type: `{delivery_type(payload, delivery)}`\n"
        f"- Executed: `{execute}`\n"
        f"- Return code: `{returncode}`\n"
        f"- Created UTC: {created}\n\n"
        f"## Detail\n\n{detail}\n",
    )
    return base.with_suffix(".json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--publisher", default="status", help="Publisher key for --latest lookup.")
    parser.add_argument("--outbox-item", default="", help="Specific outbox JSON file.")
    parser.add_argument("--latest", action="store_true", help="Deliver the latest JSON item for --publisher.")
    parser.add_argument("--execute", action="store_true", help="Perform external delivery. Default is dry-run receipt only.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    if not args.outbox_item and not args.latest:
        raise SystemExit("provide --outbox-item or --latest")
    outbox_path, payload = load_payload(root, config, args)
    delivery = configured_delivery(payload)
    returncode, detail = deliver(payload, delivery, args.execute)
    receipt = write_receipt(root, config, outbox_path, payload, delivery, args.execute, returncode, detail)
    print(relpath(root, receipt))
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
