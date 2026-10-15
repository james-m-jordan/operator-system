#!/usr/bin/env python3
"""Dry-run or execute delivery for one configured publisher outbox item."""

from __future__ import annotations

import argparse
import hashlib
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

from operator_common import load_config, memory_dir, relpath, resolve_root, write_json, write_text, workspace_lock


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
    timeout = delivery.get("timeout_seconds") if isinstance(delivery.get("timeout_seconds"), int) else 120
    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, f"delivery command timed out after {timeout}s"
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
    timeout = delivery.get("timeout_seconds") if isinstance(delivery.get("timeout_seconds"), int) else 120
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"gh issue create timed out after {timeout}s"
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
    run_id: str = "",
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
        "run_id": run_id,
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


def deliver_once(root: Path, config: dict, outbox_path: Path, payload: dict, execute: bool,
                 run_id: str = "", resolution: str = "", evidence: str = "") -> tuple[int, str]:
    delivery = configured_delivery(payload)
    identity = str(payload.get("delivery_id") or relpath(root, outbox_path))
    key = hashlib.sha256(identity.encode()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    state_path = memory_dir(root, config) / "outbox-delivery-state" / f"{key}.json"
    if not execute and not resolution:
        code, detail = deliver(payload, delivery, False)
        receipt = write_receipt(root, config, outbox_path, payload, delivery, False, code, detail, run_id)
        return code, relpath(root, receipt)
    with workspace_lock(root, config, name="delivery-" + key):
        previous = json.loads(state_path.read_text()) if state_path.exists() else {}
        if not previous:
            # Honor executed receipts created before delivery reservations existed.
            for old_path in sorted((memory_dir(root, config) / "outbox-deliveries").rglob("*.json")):
                old = json.loads(old_path.read_text())
                if old.get("outbox_item") == relpath(root, outbox_path) and old.get("executed"):
                    previous = {"delivery_id": identity, "payload_sha256": fingerprint,
                                "status": "delivered" if old.get("returncode") == 0 else "unknown",
                                "receipt": relpath(root, old_path), "legacy_receipt": True}
                    write_json(state_path, previous)
                    break
        if previous and previous.get("payload_sha256") != fingerprint:
            return 2, "outbox content changed after reservation; reconcile the original item before creating a replacement"
        if resolution:
            if previous.get("status") not in {"attempting", "unknown"}:
                return 2, "only an uncertain delivery can be reconciled"
            if not evidence.strip():
                return 2, "reconciliation requires --evidence of delivery or verified absence"
            previous["status"] = "delivered" if resolution == "delivered" else "not-delivered"
            previous.setdefault("reconciliations", []).append({"result": resolution, "evidence": evidence,
                "at": datetime.now(timezone.utc).isoformat()})
            write_json(state_path, previous)
            return 0, f"Recorded {resolution}; a verified absence permits a later explicit retry."
        if previous.get("status") == "delivered":
            return 0, f"Already delivered; receipt: {previous.get('receipt', relpath(root, state_path))}"
        if previous.get("status") in {"attempting", "unknown"}:
            return 2, "delivery is uncertain; inspect the destination and use --resolve with --evidence before retrying"
        if delivery_type(payload, delivery) in {"markdown-outbox", "task-draft", "noop"}:
            code, detail = deliver(payload, delivery, False)
            receipt = write_receipt(root, config, outbox_path, payload, delivery, False, code, detail, run_id)
            return code, relpath(root, receipt)
        state = {**previous, "delivery_id": identity, "payload_sha256": fingerprint, "status": "attempting",
                 "run_id": run_id, "reserved_utc": datetime.now(timezone.utc).isoformat()}
        write_json(state_path, state)  # Reserve before any external effect; never expire automatically.
        try:
            code, detail = deliver(payload, delivery, True)
        except Exception as exc:
            code, detail = 2, f"delivery result unknown: {type(exc).__name__}"
        state["status"] = "delivered" if code == 0 else "unknown"
        state["returncode"] = code
        receipt = write_receipt(root, config, outbox_path, payload, delivery, True, code, detail, run_id)
        state["receipt"] = relpath(root, receipt)
        write_json(state_path, state)
        return code, relpath(root, receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="")
    parser.add_argument("--publisher", default="status")
    parser.add_argument("--outbox-item", default="")
    parser.add_argument("--latest", action="store_true", help="Interactive selection only; workers should pass the exact outbox path.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--resolve", choices=["delivered", "not-delivered"], default="")
    parser.add_argument("--evidence", default="", help="Verified destination evidence for reconciliation.")
    args = parser.parse_args()
    if not args.outbox_item and not args.latest:
        parser.error("provide --outbox-item or --latest")
    if args.resolve and (args.execute or not args.outbox_item):
        parser.error("--resolve requires an exact --outbox-item and cannot be combined with --execute")
    root = resolve_root(args.root)
    config = load_config(root)
    outbox_path, payload = load_payload(root, config, args)
    code, detail = deliver_once(root, config, outbox_path, payload, args.execute, args.run_id, args.resolve, args.evidence)
    print(detail)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
