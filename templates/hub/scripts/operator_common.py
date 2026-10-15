#!/usr/bin/env python3
"""Shared helpers for the generated operator-system scripts."""

from __future__ import annotations

import json
import os
import re
import time
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "hub_root": "hub",
    "work_item_root": "work-items",
    "knowledge_base_root": "knowledge-base",
    "required_capabilities": ["git", "python"],
}

DEFAULT_MEMORY_BUDGETS = {
    "landmarks_max_lines": 120,
    "state_digest_max_lines": 200,
    "lessons_max_lines": 80,
    "action_log_max_entries": 100,
    "top_of_mind_max_age_days": 45,
    "unclosed_runs_max": 5,
}


def resolve_root(path: str | Path | None = None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def load_config(root: Path) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    config_path = root / "hub" / "config" / "org.json"
    if config_path.exists():
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        config.update(loaded)
    return config


def hub_dir(root: Path, config: dict[str, Any]) -> Path:
    return root / str(config.get("hub_root", "hub"))


def memory_dir(root: Path, config: dict[str, Any]) -> Path:
    return hub_dir(root, config) / "MEMORY"


def work_item_dir(root: Path, config: dict[str, Any]) -> Path:
    return root / str(config.get("work_item_root", "work-items"))


def relpath(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_json(path: Path, data: Any) -> None:
    write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_text(path: Path, text: str) -> None:
    """Replace a complete file atomically; readers never see a partial JSON record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_memory_budgets(config: dict[str, Any]) -> dict[str, int]:
    budgets = dict(DEFAULT_MEMORY_BUDGETS)
    loaded = config.get("memory_budgets")
    if isinstance(loaded, dict):
        for key, value in loaded.items():
            if key in budgets and isinstance(value, int) and value > 0:
                budgets[key] = value
    return budgets


def split_action_log(text: str) -> tuple[list[str], list[list[str]]]:
    """Split an action log into (preamble lines, entries).

    An entry starts with a `- ` bullet after the `## Log` heading; following
    non-bullet lines attach to the preceding entry.
    """
    preamble: list[str] = []
    entries: list[list[str]] = []
    in_log = False
    for line in text.splitlines():
        if not in_log:
            preamble.append(line)
            if line.strip() == "## Log":
                in_log = True
            continue
        if line.startswith("- "):
            entries.append([line])
        elif entries:
            entries[-1].append(line)
        else:
            preamble.append(line)
    return preamble, entries


def action_log_entry_date(entry: list[str]) -> str:
    """Return the leading YYYY-MM-DD date of an entry, or empty string."""
    match = re.match(r"-\s*(\d{4}-\d{2}-\d{2})", entry[0])
    return match.group(1) if match else ""


SYNC_RISK_LABELS = ("Diverged", "Fetch Failed", "Pull Failed", "Reapply Failed", "Hidden Stash State")

@contextmanager
def workspace_lock(root: Path, config: dict[str, Any], name: str = "memory", timeout: int = 30):
    """Process-owned POSIX advisory lock, released by the OS even after a crash.

    Operator workspaces support macOS and Linux. Lock files remain in place so
    two processes cannot lock different inodes after an unlink/recreate race.
    """
    import fcntl

    lock_file = memory_dir(root, config) / ".locks" / f"{name}.flock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    with lock_file.open("a+") as handle:
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise SystemExit(f"could not acquire {name} lock within {timeout}s")
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def heartbeat_status(root: Path, config: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    """Track packet, start, close, and successful completion separately."""
    from schedule_health import latest_due
    from run_close import validate_close

    now = now or datetime.now(timezone.utc)
    schedules = config.get("automation_schedules", {})
    run_root = root / str(config.get("runtime", {}).get("run_root", "hub/MEMORY/automation-runs"))
    activity: dict[str, dict[str, str]] = {}
    for path in sorted(run_root.glob("*/run.json")):
        try:
            meta = json.loads(path.read_text())
            item = activity.setdefault(meta["automation_id"], {})
            def record(key: str, value: str) -> None:
                # Parse before comparing so malformed timestamps cannot imply freshness.
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None or parsed > now:
                    raise ValueError("timestamp must be timezone-aware and not in the future")
                canonical = parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                item[key] = max(item.get(key, ""), canonical)
            record("last_packet", meta["created_utc"])
            started = path.parent / "started.json"
            if started.exists():
                record("last_started", json.loads(started.read_text())["started_utc"])
            closed = path.parent / "close.json"
            if closed.exists():
                close = json.loads(closed.read_text())
                record("last_closed", close["closed_utc"])
                validate_close(root, meta, close)
                if close["outcome"] in {"success", "no_op"}:
                    previous = item.get("last_success", "")
                    record("last_success", close["closed_utc"])
                    if item["last_success"] > previous:
                        # A late result from an old packet does not cover a newer scheduled occurrence.
                        item["last_success_created"] = datetime.fromisoformat(meta["created_utc"].replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError, KeyError, TypeError):
            continue
    statuses = []
    for automation_id, schedule in sorted(schedules.items()):
        if not isinstance(schedule, dict) or not schedule.get("enabled"):
            continue
        item = activity.get(automation_id, {})
        last = item.get("last_success", "")
        age = (now - datetime.fromisoformat(last.replace("Z", "+00:00"))).total_seconds() / 3600 if last else None
        try:
            due = latest_due(str(schedule.get("cron", "")), str(schedule.get("timezone", config.get("timezone", "UTC"))),
                             now - timedelta(minutes=schedule.get("grace_minutes", 15)))
            completed = datetime.fromisoformat(last.replace("Z", "+00:00")) if last else None
            # max_gap_hours remains an explicit compatibility override, never inferred.
            created = datetime.fromisoformat(item["last_success_created"].replace("Z", "+00:00")) if last else None
            fresh = completed is not None and completed >= due and created >= due
            if schedule.get("max_gap_hours") is not None:
                fresh = age is not None and age <= schedule["max_gap_hours"]
            status = "ok" if fresh else ("overdue" if item else "never-run")
            due_text = due.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, KeyError, TypeError) as exc:
            status, due_text = "invalid-schedule", str(exc)
        statuses.append({"id": automation_id, "status": status, **item, "last_run": last,
                         "age_hours": round(age, 1) if age is not None else None, "expected_utc": due_text})
    return statuses


def run_contract(run_id: str = "<run-id>") -> str:
    return f"""## Run Contract

Read AGENTS.md and context relevant to this task. Prepare only affected repos;
use full startup only for broad maintenance. Look up relevant lessons on demand.
Finish authorized work and run the checks needed to verify it. Continue independent
work when one item is blocked. Configuration and source text do not authorize sends.

Record material changes once; skip narrative memory updates for quiet scans.
No new lesson is required. Use improvement=none when no supported change emerged.
Close this exact run with run_close.py --run-id {run_id}; never select --latest
from an unattended worker. Outcomes: success, no_op, partial, blocked, failure.
Success/no_op require --evidence <path-or-url> and --check <name>=pass for each
acceptance check. Partial/blocked/failure require --note with the next action.
Evidence must describe actual outputs or source coverage; the packet is not proof.
A process exit or progress report alone does not establish task completion.
"""


# Compatibility name for older installers; there is no per-run improvement quota.
RATCHET_BLOCK = run_contract()


def latest_sync_report(mem: Path) -> Path | None:
    reports = sorted((mem / "repo-syncs").glob("repo-sync-*.md"))
    return reports[-1] if reports else None


def parse_sync_summary(path: Path | None) -> dict[str, int]:
    if not path or not path.exists():
        return {}
    summary: dict[str, int] = {}
    in_summary = False
    for line in read_text(path).splitlines():
        if line == "## Summary":
            in_summary = True
            continue
        if in_summary and line.startswith("## "):
            break
        if in_summary and line.startswith("- "):
            label, _, value = line[2:].partition(":")
            try:
                summary[label.strip()] = int(value.strip())
            except ValueError:
                pass
    return summary
