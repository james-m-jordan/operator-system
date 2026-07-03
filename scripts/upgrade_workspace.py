#!/usr/bin/env python3
"""Upgrade a scaffolded workspace with newer starter-kit templates. Dry-run by default.

Rules:

- `hub/MEMORY/` and `hub/admin-docs/` are user-owned data and are never touched.
- A workspace file is updated only when it is missing or still identical to the
  version recorded in `hub/config/template-manifest.json` at scaffold/upgrade
  time. Locally modified files are reported as conflicts and skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

DEFAULT_KIT_ROOT = Path(__file__).resolve().parents[1]
USER_OWNED_PREFIXES = ("hub/MEMORY/", "hub/admin-docs/")
MANIFEST_RELATIVE = "hub/config/template-manifest.json"


def token_map(config: dict[str, object]) -> dict[str, str]:
    return {
        "{{ORG_NAME}}": str(config.get("org_name", "Organization")),
        "{{WORKSPACE_NAME}}": str(config.get("workspace_name", "workspace")),
        "{{ADMIN_NAME}}": str(config.get("admin_name", "Admin")),
        "{{TIMEZONE}}": str(config.get("timezone", "UTC")),
        "{{PRIMARY_STATUS_CHANNEL}}": str(config.get("primary_status_channel", "#status")),
        "{{INTAKE_CHANNEL}}": str(config.get("intake_channel", "#intake")),
        "{{DATE}}": date.today().isoformat(),
    }


def render_text(text: str, tokens: dict[str, str]) -> str:
    for token, value in tokens.items():
        text = text.replace(token, value)
    return text


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def classify(target: Path, new_text: str, manifest_hash: str) -> str:
    if not target.exists():
        return "add"
    current_text = target.read_text(encoding="utf-8", errors="replace")
    if current_text == new_text:
        return "current"
    if manifest_hash and sha256_text(current_text) == manifest_hash:
        return "update"
    return "conflict"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path, help="Scaffolded workspace root.")
    parser.add_argument("--kit-root", type=Path, default=DEFAULT_KIT_ROOT, help="Starter kit root containing templates/.")
    parser.add_argument("--execute", action="store_true", help="Apply adds and updates. Without this, print the plan.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report only: write hub/MEMORY/indexes/kit-update.json and exit 1 when updates are available (for cron).",
    )
    args = parser.parse_args()
    if args.check and args.execute:
        raise SystemExit("--check and --execute are mutually exclusive")

    workspace = args.workspace.expanduser().resolve()
    template_root = args.kit_root.expanduser().resolve() / "templates"
    if not template_root.is_dir():
        raise SystemExit(f"no templates directory under kit root: {args.kit_root}")
    config = load_json(workspace / "hub" / "config" / "org.json", {})
    if not config:
        raise SystemExit(f"missing or unreadable {workspace / 'hub' / 'config' / 'org.json'}; is this a scaffolded workspace?")
    tokens = token_map(config)

    manifest_path = workspace / MANIFEST_RELATIVE
    manifest = load_json(manifest_path, {})
    manifest_files: dict[str, str] = dict(manifest.get("files", {})) if isinstance(manifest, dict) else {}
    old_version = str(manifest.get("kit_version", "unknown")) if isinstance(manifest, dict) else "unknown"
    version_path = args.kit_root.expanduser().resolve() / "VERSION"
    new_version = version_path.read_text(encoding="utf-8").strip() if version_path.exists() else "unknown"
    if not manifest_files:
        print("Note: no template manifest found; locally modified files will all be reported as conflicts.")

    plan: dict[str, list[str]] = {"add": [], "update": [], "current": [], "conflict": [], "user-owned": []}
    rendered: dict[str, str] = {}
    for source in sorted(template_root.rglob("*")):
        if source.is_dir() or "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        relative = source.relative_to(template_root).as_posix()
        if relative.startswith(USER_OWNED_PREFIXES):
            plan["user-owned"].append(relative)
            continue
        new_text = render_text(source.read_text(encoding="utf-8"), tokens)
        rendered[relative] = new_text
        status = classify(workspace / relative, new_text, manifest_files.get(relative, ""))
        plan[status].append(relative)

    print("# Workspace Upgrade Plan")
    print(f"- Workspace: {workspace}")
    print(f"- Kit templates: {template_root}")
    print(f"- Kit version: {old_version} -> {new_version}")
    for status in ["add", "update", "conflict"]:
        for relative in plan[status]:
            print(f"- {status}: {relative}")
    print(f"- Current (no change needed): {len(plan['current'])}")
    print(f"- User-owned (never touched): {len(plan['user-owned'])}")
    if plan["conflict"]:
        print("- Conflicts are locally modified files; merge kit changes by hand if wanted.")

    if args.check:
        marker = {
            "checked": tokens["{{DATE}}"],
            "kit_version_current": old_version,
            "kit_version_available": new_version,
            "adds": len(plan["add"]),
            "updates": len(plan["update"]),
            "conflicts": len(plan["conflict"]),
        }
        marker_path = workspace / str(config.get("hub_root", "hub")) / "MEMORY" / "indexes" / "kit-update.json"
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        available = bool(plan["add"] or plan["update"])
        print(f"- Update available: {'yes' if available else 'no'} (marker: {marker_path})")
        return 1 if available else 0

    if not args.execute:
        print("- Dry run. Re-run with --execute to apply adds and updates.")
        return 0

    for relative in plan["add"] + plan["update"]:
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered[relative], encoding="utf-8")
        manifest_files[relative] = sha256_text(rendered[relative])
    for relative in plan["current"]:
        manifest_files.setdefault(relative, sha256_text(rendered[relative]))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"generated": tokens["{{DATE}}"], "kit_version": new_version, "files": manifest_files},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    stale_marker = workspace / str(config.get("hub_root", "hub")) / "MEMORY" / "indexes" / "kit-update.json"
    stale_marker.unlink(missing_ok=True)
    print(f"Applied {len(plan['add'])} adds and {len(plan['update'])} updates; refreshed {MANIFEST_RELATIVE}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
