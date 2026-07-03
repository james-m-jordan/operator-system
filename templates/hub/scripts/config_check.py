#!/usr/bin/env python3
"""Validate hub/config/org.json before other scripts trip over mistakes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import DEFAULT_MEMORY_BUDGETS, load_config, resolve_root

KNOWN_TOP_LEVEL = {
    "org_name", "workspace_name", "admin_name", "timezone", "primary_status_channel",
    "intake_channel", "work_item_label", "work_item_root", "knowledge_base_root",
    "hub_root", "connectors", "required_capabilities", "optional_commands", "sync_skip",
    "memory_budgets", "feeds", "file_sources", "backup", "runtime",
    "automation_schedules", "automations", "roles", "retention",
    "generated_from", "generated_from_version",
}
KNOWN_DELIVERY_TYPES = {"slack-webhook", "webhook-json", "github-issue", "command", "markdown-outbox", "task-draft", "noop"}
KNOWN_PROVIDER_TYPES = {"direct-url", "slack-web-api", "command"}
KNOWN_TRANSFER_METHODS = {"local-copy", "rsync"}


def check_config(config: dict[str, object], raw: dict[str, object]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for key in ("org_name", "workspace_name", "hub_root", "work_item_root", "knowledge_base_root"):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key}: must be a non-empty string")

    for key in raw:
        if key not in KNOWN_TOP_LEVEL:
            warnings.append(f"unknown top-level key: {key}")

    budgets = config.get("memory_budgets")
    if budgets is not None:
        if not isinstance(budgets, dict):
            errors.append("memory_budgets: must be an object")
        else:
            for key, value in budgets.items():
                if key not in DEFAULT_MEMORY_BUDGETS:
                    warnings.append(f"memory_budgets.{key}: unknown budget key")
                if not isinstance(value, int) or value <= 0:
                    errors.append(f"memory_budgets.{key}: must be a positive integer")

    schedules = config.get("automation_schedules")
    if schedules is not None:
        if not isinstance(schedules, dict):
            errors.append("automation_schedules: must be an object")
        else:
            for automation_id, schedule in schedules.items():
                if not isinstance(schedule, dict):
                    errors.append(f"automation_schedules.{automation_id}: must be an object")
                    continue
                cron = str(schedule.get("cron", ""))
                if len(cron.split()) != 5:
                    errors.append(f"automation_schedules.{automation_id}.cron: expected 5 cron fields, got {cron!r}")
                if not isinstance(schedule.get("enabled"), bool):
                    warnings.append(f"automation_schedules.{automation_id}.enabled: should be true or false")
                max_gap = schedule.get("max_gap_hours")
                if max_gap is not None and (not isinstance(max_gap, int) or max_gap <= 0):
                    errors.append(f"automation_schedules.{automation_id}.max_gap_hours: must be a positive integer")

    runtime = config.get("runtime")
    if runtime is not None:
        if not isinstance(runtime, dict):
            errors.append("runtime: must be an object")
        else:
            command = runtime.get("agent_command")
            if command is not None and not (isinstance(command, list) and command and all(isinstance(part, str) for part in command)):
                errors.append("runtime.agent_command: must be a non-empty list of strings")
            timeout = runtime.get("agent_timeout_seconds")
            if timeout is not None and (not isinstance(timeout, int) or timeout <= 0):
                errors.append("runtime.agent_timeout_seconds: must be a positive integer")
            targets = runtime.get("publisher_targets", {})
            if isinstance(targets, dict):
                for name, target in targets.items():
                    if not isinstance(target, dict):
                        errors.append(f"runtime.publisher_targets.{name}: must be an object")
                        continue
                    delivery = target.get("delivery")
                    if isinstance(delivery, dict):
                        delivery_type = str(delivery.get("type", ""))
                        if delivery_type and delivery_type not in KNOWN_DELIVERY_TYPES:
                            errors.append(
                                f"runtime.publisher_targets.{name}.delivery.type: unknown type {delivery_type!r} "
                                f"(known: {', '.join(sorted(KNOWN_DELIVERY_TYPES))})"
                            )

    backup = config.get("backup")
    if isinstance(backup, dict):
        transfer = backup.get("transfer")
        if isinstance(transfer, dict):
            method = str(transfer.get("method", "local-copy"))
            if method not in KNOWN_TRANSFER_METHODS:
                errors.append(f"backup.transfer.method: unknown method {method!r} (known: {', '.join(sorted(KNOWN_TRANSFER_METHODS))})")
            if not str(transfer.get("destination", "")).strip():
                warnings.append("backup.transfer.destination: empty; backup_transfer.py will require --destination")

    file_sources = config.get("file_sources")
    if isinstance(file_sources, dict):
        chat = file_sources.get("chat")
        if isinstance(chat, dict):
            providers = chat.get("providers", {})
            if isinstance(providers, dict):
                for name, provider in providers.items():
                    provider_type = str(provider.get("type", "")) if isinstance(provider, dict) else ""
                    if provider_type not in KNOWN_PROVIDER_TYPES:
                        errors.append(f"file_sources.chat.providers.{name}.type: unknown type {provider_type!r}")

    feeds = config.get("feeds")
    if feeds is not None:
        if not isinstance(feeds, dict):
            errors.append("feeds: must be an object")
        else:
            for key in ("sources", "topics"):
                value = feeds.get(key)
                if value is not None and not (isinstance(value, list) and all(isinstance(item, str) for item in value)):
                    errors.append(f"feeds.{key}: must be a list of strings")

    retention = config.get("retention")
    if retention is not None:
        if not isinstance(retention, dict):
            errors.append("retention: must be an object")
        else:
            days = retention.get("days")
            if days is not None and (not isinstance(days, int) or days <= 0):
                errors.append("retention.days: must be a positive integer")
            targets = retention.get("targets")
            if targets is not None and not (isinstance(targets, list) and all(isinstance(item, str) for item in targets)):
                errors.append("retention.targets: must be a list of strings")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--json", action="store_true", help="Print JSON result.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config_path = root / "hub" / "config" / "org.json"
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"missing {config_path}")
        return 1
    except json.JSONDecodeError as exc:
        print(f"invalid JSON in {config_path}: {exc}")
        return 1

    config = load_config(root)
    errors, warnings = check_config(config, raw)
    if args.json:
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, indent=2))
    else:
        print(f"# Config Check: {'PASS' if not errors else 'FAIL'}")
        for error in errors:
            print(f"- error: {error}")
        for warning in warnings:
            print(f"- warning: {warning}")
        if not errors and not warnings:
            print("- No issues found.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
