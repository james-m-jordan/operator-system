#!/usr/bin/env python3
"""Check explicitly selected write dependencies without a workspace-wide refresh."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from config_check import check_config
from operator_common import load_config, relpath, resolve_root
from preflight_capabilities import check_command, check_env_var, check_git, check_github_cli, check_python
from sync_workspace import discover_repos, status_for_repo


def selected_repos(root: Path, paths: list[str]) -> list[Path]:
    root = root.resolve()
    repos: set[Path] = set()
    for value in paths:
        path = (root / value).resolve()
        if not path.is_relative_to(root) or not path.is_dir():
            raise ValueError(f"dependency must be an existing directory inside the workspace: {value}")
        owner = next((p for p in [path, *path.parents] if p.is_relative_to(root) and (p / '.git').exists()), None)
        if owner:
            repos.add(owner)
        else:
            repos.update(discover_repos(path, set()))
    return sorted(repos)


def capability(name: str) -> dict[str, object]:
    checks = {"python": check_python, "git": check_git, "github_cli": check_github_cli}
    if name in checks:
        return checks[name]()
    if name.startswith("env:"):
        return check_env_var(name[4:])
    if name.startswith("command:"):
        return check_command(name[8:])
    return {"ok": False, "detail": "unknown capability; use python, git, github_cli, env:<name>, or command:<name>"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="")
    parser.add_argument("--repo", action="append", required=True, help="Affected repo or folder; repeat for dependencies.")
    parser.add_argument("--capability", action="append", default=[], help="Required check; default python and git.")
    args = parser.parse_args()
    root = resolve_root(args.root)
    raw = json.loads((root / "hub/config/org.json").read_text())
    config = load_config(root)
    errors, warnings = check_config(config, raw)
    try:
        repos = selected_repos(root, args.repo)
    except ValueError as exc:
        errors.append(str(exc))
        repos = []
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2))
        return 1
    checks = {name: capability(name) for name in sorted(set(args.capability or ["python", "git"]))}
    if any(not item["ok"] for item in checks.values()):
        print(json.dumps({"ok": False, "capabilities": checks}, indent=2))
        return 1
    results = [status_for_repo(root, repo, execute=False) for repo in repos]
    safe = {"up_to_date", "dirty_local_only", "ahead_local", "no_upstream"}
    blocked = [item.repo for item in results if item.action not in safe]
    print(json.dumps({"ok": not blocked, "scope": args.repo, "capabilities": checks,
                      "repos": [vars(item) for item in results], "blocked": blocked,
                      "warnings": warnings}, indent=2))
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
