#!/usr/bin/env python3
"""Shared helpers for the generated operator-system scripts."""

from __future__ import annotations

import json
import re
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
