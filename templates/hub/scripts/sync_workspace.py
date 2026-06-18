#!/usr/bin/env python3
"""Fetch nested git repositories and write a sync-health report."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import load_config, memory_dir, relpath, resolve_root, write_text


GIT_TIMEOUT_SECONDS = 45


@dataclass(frozen=True)
class RepoStatus:
    repo: str
    branch: str
    upstream: str
    ahead: int
    behind: int
    dirty: bool
    action: str
    detail: str
    sample_paths: tuple[str, ...]
    stash_count: int


def git_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=15")
    return env


def run_git(repo: Path, args: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env=git_env(),
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"git {' '.join(args)} timed out after {GIT_TIMEOUT_SECONDS}s"


def discover_repos(root: Path, skip: set[str]) -> list[Path]:
    repos = []
    for git_dir in sorted(root.rglob(".git")):
        repo = git_dir.parent
        rel = relpath(root, repo)
        if rel in skip or any(rel.startswith(prefix.rstrip("/") + "/") for prefix in skip):
            continue
        repos.append(repo)
    return repos


def dirty_paths(repo: Path) -> tuple[bool, tuple[str, ...]]:
    rc, out, _ = run_git(repo, ["status", "--porcelain"])
    if rc != 0:
        return False, ()
    lines = [line for line in out.splitlines() if line.strip()]
    return bool(lines), tuple(line[2:].strip() for line in lines[:6])


def stash_count(repo: Path) -> int:
    rc, out, _ = run_git(repo, ["stash", "list"])
    if rc != 0 or not out:
        return 0
    return len([line for line in out.splitlines() if line.strip()])


def upstream_parts(upstream: str) -> tuple[str, str]:
    if "/" not in upstream:
        return "origin", upstream
    return upstream.split("/", 1)


def stash_pull_pop(repo: Path, remote: str, branch: str) -> tuple[bool, str]:
    message = f"operator-auto-sync-{date.today().isoformat()}"
    rc, _, err = run_git(repo, ["stash", "push", "--include-untracked", "-m", message])
    if rc != 0:
        return False, err or "Failed to stash local changes."
    rc, _, err = run_git(repo, ["pull", "--ff-only", remote, branch])
    if rc != 0:
        return False, err or "Fast-forward pull failed after stashing."
    rc, _, err = run_git(repo, ["stash", "pop"])
    if rc != 0:
        return False, err or "Stash pop reported conflicts."
    return True, "Stashed local changes, fast-forwarded, and reapplied the stash."


def status_for_repo(root: Path, repo: Path) -> RepoStatus:
    repo_rel = relpath(root, repo)
    _, branch, _ = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    dirty, samples = dirty_paths(repo)
    up_rc, upstream, up_err = run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    if up_rc != 0 or not upstream:
        return RepoStatus(repo_rel, branch or "unknown", "", 0, 0, dirty, "no_upstream", up_err or "No upstream configured.", samples, stash_count(repo))

    remote, remote_branch = upstream_parts(upstream)
    fetch_rc, _, fetch_err = run_git(repo, ["fetch", remote])
    if fetch_rc != 0:
        return RepoStatus(repo_rel, branch, upstream, 0, 0, dirty, "fetch_failed", fetch_err or "Fetch failed.", samples, stash_count(repo))

    counts_rc, counts, counts_err = run_git(repo, ["rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
    if counts_rc != 0 or not counts:
        return RepoStatus(repo_rel, branch, upstream, 0, 0, dirty, "status_failed", counts_err or "Could not compute ahead/behind.", samples, stash_count(repo))

    ahead, behind = [int(part) for part in counts.split()]
    if ahead and behind:
        return RepoStatus(repo_rel, branch, upstream, ahead, behind, dirty, "diverged", "Local branch has diverged from upstream.", samples, stash_count(repo))
    if dirty and behind and not ahead:
        ok, detail = stash_pull_pop(repo, remote, remote_branch)
        return RepoStatus(repo_rel, branch, upstream, 0 if ok else ahead, 0 if ok else behind, True, "synced_dirty" if ok else "reapply_failed", detail, samples, stash_count(repo))
    if dirty:
        return RepoStatus(repo_rel, branch, upstream, ahead, behind, True, "dirty_local_only", "Local worktree is dirty, but upstream is already merged.", samples, stash_count(repo))
    if ahead:
        return RepoStatus(repo_rel, branch, upstream, ahead, behind, False, "ahead_local", "Local branch is ahead of upstream.", (), stash_count(repo))
    if not behind:
        return RepoStatus(repo_rel, branch, upstream, ahead, behind, False, "up_to_date", "Already aligned to upstream.", (), stash_count(repo))

    _, old_head, _ = run_git(repo, ["rev-parse", "--short", "HEAD"])
    pull_rc, _, pull_err = run_git(repo, ["pull", "--ff-only", remote, remote_branch])
    if pull_rc != 0:
        return RepoStatus(repo_rel, branch, upstream, ahead, behind, False, "pull_failed", pull_err or "Pull failed.", (), stash_count(repo))
    _, new_head, _ = run_git(repo, ["rev-parse", "--short", "HEAD"])
    return RepoStatus(repo_rel, branch, upstream, 0, 0, False, "synced", f"Fast-forwarded {old_head} -> {new_head}.", (), stash_count(repo))


def render_report(results: list[RepoStatus]) -> str:
    order = [
        ("synced_dirty", "Synced Through Dirty Worktree"),
        ("synced", "Synced"),
        ("up_to_date", "Already Up To Date"),
        ("dirty_local_only", "Dirty But Already Synced"),
        ("ahead_local", "Ahead Of Upstream"),
        ("diverged", "Diverged"),
        ("no_upstream", "Missing Upstream"),
        ("fetch_failed", "Fetch Failed"),
        ("status_failed", "Status Failed"),
        ("pull_failed", "Pull Failed"),
        ("reapply_failed", "Reapply Failed"),
    ]
    grouped = {key: [item for item in results if item.action == key] for key, _ in order}
    lines = ["# Repo Sync Report", "", f"- Generated: {date.today().isoformat()}", "", "## Summary", ""]
    for key, label in order:
        lines.append(f"- {label}: {len(grouped[key])}")
    lines.append(f"- Hidden Stash State: {sum(1 for item in results if item.stash_count)}")
    lines.append("")
    for key, label in order:
        lines.extend([f"## {label}", ""])
        if not grouped[key]:
            lines.extend(["- None.", ""])
            continue
        for item in sorted(grouped[key], key=lambda value: value.repo):
            lines.extend([
                f"### {item.repo}",
                "",
                f"- Branch: `{item.branch}`",
                f"- Upstream: `{item.upstream or '(none)'}`",
                f"- Ahead/behind before action: `{item.ahead}` / `{item.behind}`",
                f"- Dirty: `{item.dirty}`",
                f"- Stash entries after action: `{item.stash_count}`",
                f"- Detail: {item.detail}",
            ])
            if item.sample_paths:
                lines.append("- Example local-change paths:")
                lines.extend(f"  - `{path}`" for path in item.sample_paths)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--output", default="", help="Report path. Defaults to hub/MEMORY/repo-syncs/repo-sync-YYYY-MM-DD.md.")
    args = parser.parse_args()

    root = resolve_root(args.root)
    config = load_config(root)
    skip = set(config.get("sync_skip", []) or [])
    results = [status_for_repo(root, repo) for repo in discover_repos(root, skip)]
    output = Path(args.output) if args.output else memory_dir(root, config) / "repo-syncs" / f"repo-sync-{date.today().isoformat()}.md"
    if not output.is_absolute():
        output = root / output
    write_text(output, render_report(results))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
