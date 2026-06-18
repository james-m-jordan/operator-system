#!/usr/bin/env python3
"""Shared helpers for the generated operator-system scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "hub_root": "hub",
    "work_item_root": "work-items",
    "knowledge_base_root": "knowledge-base",
    "required_capabilities": ["git", "python"],
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
