#!/usr/bin/env python3
"""Shared helpers for the generated operator-system scripts."""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
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
    "runs_without_improvement_max": 5,
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_memory_budgets(config: dict[str, Any]) -> dict[str, int]:
    budgets = dict(DEFAULT_MEMORY_BUDGETS)
    loaded = config.get("memory_budgets")
    if isinstance(loaded, dict):
        for key, value in loaded.items():
            if isinstance(value, int) and value > 0:
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

LOCK_STALE_SECONDS = 600


@contextmanager
def workspace_lock(root: Path, config: dict[str, Any], name: str = "memory", timeout: int = 30):
    """Cross-process lock for shared memory files. Breaks stale locks."""
    lock_dir = memory_dir(root, config) / ".locks" / f"{name}.lock"
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            lock_dir.mkdir()
            (lock_dir / "owner").write_text(f"{os.getpid()} {time.time()}\n", encoding="utf-8")
            break
        except FileExistsError:
            try:
                stamp = float((lock_dir / "owner").read_text(encoding="utf-8").split()[1])
            except Exception:
                stamp = 0.0
            if time.time() - stamp > LOCK_STALE_SECONDS:
                try:
                    (lock_dir / "owner").unlink(missing_ok=True)
                    lock_dir.rmdir()
                except OSError:
                    pass
                continue
            if time.monotonic() > deadline:
                raise SystemExit(f"could not acquire {name} lock within {timeout}s; another run holds {lock_dir}")
            time.sleep(0.2)
    try:
        yield
    finally:
        try:
            (lock_dir / "owner").unlink(missing_ok=True)
            lock_dir.rmdir()
        except OSError:
            pass


def cron_max_gap_hours(cron: str) -> int:
    """Coarse expected max gap between runs for a cron expression."""
    fields = cron.split()
    if len(fields) != 5:
        return 26
    _, hour, day_of_month, _, day_of_week = fields
    if day_of_month != "*":
        return 32 * 24
    if day_of_week != "*":
        return 8 * 24
    if hour != "*":
        return 26
    return 3


def heartbeat_status(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Per enabled automation schedule: last run recency vs expected cadence."""
    schedules = config.get("automation_schedules", {})
    if not isinstance(schedules, dict):
        return []
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    run_root = root / str(runtime.get("run_root", "hub/MEMORY/automation-runs"))
    last_run: dict[str, str] = {}
    if run_root.exists():
        for child in sorted(run_root.iterdir()):
            try:
                meta = json.loads((child / "run.json").read_text(encoding="utf-8"))
            except Exception:
                continue
            automation_id = str(meta.get("automation_id", ""))
            created = str(meta.get("created_utc", ""))
            if automation_id and created > last_run.get(automation_id, ""):
                last_run[automation_id] = created
    now = datetime.now(timezone.utc)
    statuses = []
    for automation_id, schedule in sorted(schedules.items()):
        if not isinstance(schedule, dict) or not schedule.get("enabled"):
            continue
        max_gap = schedule.get("max_gap_hours") or cron_max_gap_hours(str(schedule.get("cron", "")))
        last = last_run.get(automation_id, "")
        status = "never-run"
        age_hours = 0.0
        if last:
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                age_hours = (now - last_dt).total_seconds() / 3600
                status = "overdue" if age_hours > max_gap else "ok"
            except ValueError:
                status = "unreadable"
        statuses.append(
            {"id": automation_id, "status": status, "last_run": last, "age_hours": round(age_hours, 1), "max_gap_hours": max_gap}
        )
    return statuses

RATCHET_BLOCK = """## Standard Ratchet

Before acting, read all of `hub/MEMORY/LESSONS.md` and apply the active
lessons. Before closing the run:

1. Record the run in `hub/MEMORY/agent-action-log.md`.
2. Leave one improvement: add or re-confirm a lesson in
   `hub/MEMORY/LESSONS.md`, correct one wrong memory entry, or prune one
   stale entry.
3. Refresh memory health and fix any budget violation you introduced:
   `python3 hub/scripts/memory_health.py --root . --write`
4. Close the run record:
   `python3 hub/scripts/run_close.py --root . --latest --outcome <success|partial|failure> --improvement <lesson|correction|pruning|promotion>`
"""


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
