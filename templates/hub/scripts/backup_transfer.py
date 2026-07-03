#!/usr/bin/env python3
"""Plan or execute a config-driven workspace backup transfer."""

from __future__ import annotations

import argparse
import fnmatch
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, memory_dir, relpath, resolve_root, write_text


DEFAULT_REQUIRED_PATHS = ["AGENTS.md", "hub", "work-items", "knowledge-base"]


def backup_config(config: dict[str, object]) -> dict[str, object]:
    return config.get("backup", {}) if isinstance(config.get("backup"), dict) else {}


def transfer_config(config: dict[str, object]) -> dict[str, object]:
    backup = backup_config(config)
    return backup.get("transfer", {}) if isinstance(backup.get("transfer"), dict) else {}


def normalize_patterns(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value).rstrip("/") for value in values]


def required_paths(config: dict[str, object]) -> list[str]:
    backup = backup_config(config)
    values = backup.get("required_paths", DEFAULT_REQUIRED_PATHS)
    if not isinstance(values, list):
        return DEFAULT_REQUIRED_PATHS
    return [str(value).strip("/") for value in values]


def exclude_patterns(config: dict[str, object]) -> list[str]:
    backup = backup_config(config)
    return normalize_patterns(backup.get("exclude", []))


def missing_required(root: Path, required: list[str]) -> list[str]:
    return [relative for relative in required if not (root / relative).exists()]


def raw_destination(config: dict[str, object], override: str) -> str:
    transfer = transfer_config(config)
    destination = override or str(transfer.get("destination", ""))
    if not destination:
        raise SystemExit("backup destination is required; set backup.transfer.destination or pass --destination")
    return destination


def is_remote_rsync_destination(value: str) -> bool:
    return ":" in value and not value.startswith("/") and "://" not in value


def destination_value(root: Path, config: dict[str, object], override: str, method: str) -> Path | str:
    destination = raw_destination(config, override)
    if method == "rsync" and is_remote_rsync_destination(destination):
        return destination
    path = Path(destination).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def method_name(config: dict[str, object], override: str) -> str:
    transfer = transfer_config(config)
    return override or str(transfer.get("method", "local-copy"))


def excluded(relative: str, patterns: list[str]) -> bool:
    relative = relative.strip("/")
    for pattern in patterns:
        pattern = pattern.strip("/")
        if not pattern:
            continue
        if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(relative + "/", pattern + "/"):
            return True
        if relative.startswith(pattern.rstrip("/") + "/"):
            return True
    return False


def copy_one(root: Path, destination: Path, relative: str, patterns: list[str]) -> list[str]:
    source = root / relative
    target = destination / relative
    copied: list[str] = []
    if source.is_file():
        if not excluded(relative, patterns):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(relative)
        return copied
    for path in sorted(source.rglob("*")):
        item_relative = path.relative_to(root).as_posix()
        if excluded(item_relative, patterns):
            continue
        target = destination / item_relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied.append(item_relative)
    return copied


def rsync_command(root: Path, destination: Path | str, required: list[str], patterns: list[str], execute: bool) -> list[str]:
    command = ["rsync", "-a"]
    if not execute:
        command.append("--dry-run")
    for pattern in patterns:
        command.extend(["--exclude", pattern])
    for relative in required:
        command.append(str(root / relative))
    command.append(str(destination))
    return command


def run_transfer(
    root: Path,
    destination: Path | str,
    required: list[str],
    patterns: list[str],
    method: str,
    execute: bool,
    timeout_seconds: int = 3600,
) -> tuple[int, str, list[str]]:
    if method == "local-copy":
        if not isinstance(destination, Path):
            return 2, "local-copy requires a local filesystem destination", []
        if not execute:
            planned = [relative for relative in required if not excluded(relative, patterns)]
            return 0, f"dry-run local copy to {destination}", planned
        destination.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for relative in required:
            if excluded(relative, patterns):
                continue
            copied.extend(copy_one(root, destination, relative, patterns))
        return 0, f"copied {len(copied)} files to {destination}", copied
    if method == "rsync":
        command = rsync_command(root, destination, required, patterns, execute)
        if not execute:
            return 0, "dry-run rsync command: " + shlex.join(command), required
        if isinstance(destination, Path):
            destination.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            return 124, f"rsync timed out after {timeout_seconds}s", required
        detail = (result.stdout + result.stderr).strip()
        return result.returncode, detail[:2000], required
    return 2, f"unsupported backup transfer method: {method}", []


def render_report(
    root: Path,
    destination: Path | str,
    required: list[str],
    patterns: list[str],
    method: str,
    execute: bool,
    returncode: int,
    detail: str,
    copied: list[str],
    missing: list[str],
    run_id: str = "",
) -> str:
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = ["# Backup Transfer Report", ""]
    lines.append(f"- Created UTC: {created}")
    lines.append(f"- Source: `{root}`")
    lines.append(f"- Destination: `{destination}`")
    lines.append(f"- Method: `{method}`")
    lines.append(f"- Executed: `{execute}`")
    lines.append(f"- Return code: `{returncode}`")
    if run_id:
        lines.append(f"- Automation run: `{run_id}`")
    lines.append("")
    lines.append("## Required Paths")
    lines.append("")
    for relative in required:
        status = "MISSING" if relative in missing else "OK"
        lines.append(f"- {status} `{relative}`")
    lines.append("")
    lines.append("## Excludes")
    lines.append("")
    if patterns:
        for pattern in patterns:
            lines.append(f"- `{pattern}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Transfer Detail")
    lines.append("")
    lines.append(detail or "No detail.")
    if copied:
        lines.append("")
        lines.append("## Planned/Copied Paths")
        lines.append("")
        for relative in copied[:200]:
            lines.append(f"- `{relative}`")
        if len(copied) > 200:
            lines.append(f"- ... {len(copied) - 200} additional paths omitted")
    result = "PASS" if returncode == 0 and not missing else "BLOCKED"
    lines.append("")
    lines.append(f"## Result\n\n{result}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--destination", default="", help="Backup destination override.")
    parser.add_argument("--method", default="", choices=["", "local-copy", "rsync"], help="Transfer method override.")
    parser.add_argument("--execute", action="store_true", help="Execute transfer. Default only writes a dry-run plan.")
    parser.add_argument("--write-report", "--write", dest="write_report", action="store_true", help="Write report under hub/MEMORY/backups/.")
    parser.add_argument("--run-id", default="", help="Automation run ID this transfer belongs to; recorded in the report.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    required = required_paths(config)
    patterns = exclude_patterns(config)
    missing = missing_required(root, required)
    method = method_name(config, args.method)
    destination = destination_value(root, config, args.destination, method)
    transfer = transfer_config(config)
    timeout_seconds = transfer.get("timeout_seconds") if isinstance(transfer.get("timeout_seconds"), int) else 3600
    if missing:
        returncode, detail, copied = 1, "required source paths are missing", []
    else:
        returncode, detail, copied = run_transfer(root, destination, required, patterns, method, args.execute, timeout_seconds)
    report = render_report(root, destination, required, patterns, method, args.execute, returncode, detail, copied, missing, args.run_id)
    if args.write_report:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        out = memory_dir(root, config) / "backups" / f"backup-transfer-{timestamp}.md"
        write_text(out, report)
        print(relpath(root, out))
    else:
        print(report, end="")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
