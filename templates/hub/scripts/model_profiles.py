#!/usr/bin/env python3
"""Resolve explicit model/provider profiles into local agent CLI invocations."""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

from operator_common import load_config, resolve_root


EFFORTS = ("low", "medium", "high", "xhigh", "max")
BUILTIN_PROFILES = {
    "gpt-6-astra": {
        "provider": "openai", "model": "gpt-6-astra", "effort": "medium",
        "executable": "codex", "timeout_seconds": 3600, "sandbox": "workspace-write",
    },
    "claude-opus-5-5": {
        "provider": "anthropic", "model": "claude-opus-5-5", "effort": "medium",
        "executable": "claude", "timeout_seconds": 3600, "permission_mode": "dontAsk",
    },
}
MODELS = {"openai": "gpt-6-astra", "anthropic": "claude-opus-5-5"}
COMMON_FIELDS = {"provider", "model", "effort", "executable", "timeout_seconds"}
PROVIDER_FIELDS = {
    "openai": {"sandbox"}, "anthropic": {"permission_mode", "allowed_tools"},
}


def positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def profile_catalog(config: dict) -> dict:
    """Built-ins also work in upgraded workspaces whose config is preserved."""
    runtime = config.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError("runtime: must be an object")
    overrides = runtime.get("model_profiles", {})
    if not isinstance(overrides, dict):
        raise ValueError("runtime.model_profiles: must be an object")
    profiles = copy.deepcopy(BUILTIN_PROFILES)
    for name, value in overrides.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
            raise ValueError("profile names must contain only letters, digits, dots, underscores, or hyphens")
        if not isinstance(value, dict):
            raise ValueError(f"runtime.model_profiles.{name}: must be an object")
        profiles[name] = {**profiles.get(name, {}), **value}
    for name, profile in profiles.items():
        label = f"runtime.model_profiles.{name}"
        provider = profile.get("provider")
        if not isinstance(provider, str) or provider not in MODELS:
            raise ValueError(f"{label}.provider: expected openai or anthropic")
        unknown = set(profile) - COMMON_FIELDS - PROVIDER_FIELDS[provider]
        if unknown:
            raise ValueError(f"{label}: unsupported fields: {', '.join(sorted(unknown))}")
        if profile.get("model") != MODELS[provider]:
            raise ValueError(f"{label}.model: {provider} requires exact model {MODELS[provider]}")
        if profile.get("effort") not in EFFORTS:
            raise ValueError(f"{label}.effort: expected one of {', '.join(EFFORTS)}")
        profile.setdefault("executable", "codex" if provider == "openai" else "claude")
        executable = profile["executable"]
        if not isinstance(executable, str) or not executable.strip() or "\x00" in executable or executable.startswith("-"):
            raise ValueError(f"{label}.executable: expected an executable name or path, not shell text")
        profile.setdefault("timeout_seconds", runtime.get("agent_timeout_seconds", 3600))
        if not positive_integer(profile["timeout_seconds"]):
            raise ValueError(f"{label}.timeout_seconds: must be a positive integer")
        if provider == "openai":
            profile.setdefault("sandbox", "workspace-write")
            if profile["sandbox"] not in ("read-only", "workspace-write"):
                raise ValueError(f"{label}.sandbox: expected read-only or workspace-write")
        else:
            profile.setdefault("permission_mode", "dontAsk")
            if profile["permission_mode"] not in ("dontAsk", "acceptEdits", "auto"):
                raise ValueError(f"{label}.permission_mode: expected dontAsk, acceptEdits, or auto")
            allowed = profile.get("allowed_tools", [])
            if not isinstance(allowed, list) or not all(isinstance(t, str) and t.strip() and not t.startswith("-") for t in allowed):
                raise ValueError(f"{label}.allowed_tools: expected a list of nonempty tool permission rules")
    return profiles


def validate_profiles(config: dict) -> list[str]:
    try:
        profiles = profile_catalog(config)
        runtime = config.get("runtime", {})
        default = runtime.get("default_profile")
        if default is not None and (not isinstance(default, str) or default not in profiles):
            raise ValueError("runtime.default_profile: must name a known profile or be null")
        routes = runtime.get("automation_profiles", {})
        if not isinstance(routes, dict):
            raise ValueError("runtime.automation_profiles: must be an object")
        for automation_id, name in routes.items():
            if not isinstance(automation_id, str) or not automation_id.strip():
                raise ValueError("runtime.automation_profiles: automation IDs must be nonempty strings")
            if not isinstance(name, str) or name not in profiles:
                raise ValueError(f"runtime.automation_profiles.{automation_id}: unknown profile")
            if "automations" in config and automation_id not in config["automations"]:
                raise ValueError(f"runtime.automation_profiles.{automation_id}: not in configured automations")
        return []
    except (ValueError, TypeError) as exc:
        return [str(exc)]


def profile_command(profile: dict) -> list[str]:
    if profile["provider"] == "openai":
        return [profile["executable"], "exec", "--model", profile["model"],
                "--config", 'model_provider="openai"',
                "--config", f'model_reasoning_effort="{profile["effort"]}"',
                "--config", 'approval_policy="never"', "--sandbox", profile["sandbox"],
                "--skip-git-repo-check", "-"]
    command = [profile["executable"], "--print", "--model", profile["model"],
               "--effort", profile["effort"], "--permission-mode", profile["permission_mode"],
               "--permission-prompts", "none", "--output-format", "text",
               "--settings", '{"fallbackModel":[]}']
    if profile.get("allowed_tools"):
        command.extend(["--allowedTools", *profile["allowed_tools"]])
    return command


def resolve_execution(config: dict, automation_id: str = "", profile_name: str | None = None,
                      packet_path: Path | str = "{packet}") -> dict:
    errors = validate_profiles(config)
    if errors:
        raise ValueError("; ".join(errors))
    runtime = config.get("runtime", {})
    routes = runtime.get("automation_profiles", {})
    name = profile_name if profile_name is not None else routes.get(automation_id, runtime.get("default_profile"))
    selected_by = "command-line" if profile_name is not None else ("automation" if automation_id in routes else "default")
    if name is not None:
        profiles = profile_catalog(config)
        if name not in profiles:
            raise ValueError(f"unknown model profile: {name}")
        profile = profiles[name]
        return {"profile": name, "selected_by": selected_by, **profile, "command": profile_command(profile)}
    command = runtime.get("agent_command")
    if not isinstance(command, list) or not command or not all(isinstance(p, str) and "\x00" not in p for p in command) or not command[0].strip():
        raise ValueError("no valid runtime.agent_command; select --profile gpt-6-astra or claude-opus-5-5, or configure an argv wrapper")
    timeout = runtime.get("agent_timeout_seconds", 3600)
    if not positive_integer(timeout):
        raise ValueError("runtime.agent_timeout_seconds: must be a positive integer")
    return {"profile": None, "provider": "command", "selected_by": "legacy",
            "timeout_seconds": timeout, "command": [p.replace("{packet}", str(packet_path)) for p in command]}


def check_runtime(execution: dict, root: Path) -> dict:
    """Offline interface check only: never contacts a model or reads credentials."""
    executable = execution["command"][0]
    candidate = Path(executable)
    found = str(root / candidate) if "/" in executable and not candidate.is_absolute() else executable
    if not shutil.which(found):
        return {"ok": False, "detail": f"{executable} not found; install the provider CLI or set profile.executable"}
    if execution["provider"] == "command":
        return {"ok": True, "detail": "custom command found; wrapper interface is user-managed"}
    flags = (["exec", "--help"] if execution["provider"] == "openai" else ["--help"])
    required = (["--model", "--config", "--sandbox", "--skip-git-repo-check"] if execution["provider"] == "openai"
                else ["--print", "--model", "--effort", "--permission-mode", "--permission-prompts", "--output-format", "--settings"])
    if execution.get("allowed_tools"):
        required.append("--allowedTools")
    try:
        result = subprocess.run([found, *flags], cwd=root, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "detail": f"CLI interface check failed: {type(exc).__name__}"}
    output = result.stdout + result.stderr
    missing = [flag for flag in required if flag not in output]
    if result.returncode or missing:
        return {"ok": False, "detail": f"incompatible {executable}; update the CLI (missing flags: {', '.join(missing) or 'help command failed'})"}
    return {"ok": True, "detail": "CLI flags available; account/model access and task permissions are not verified"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="")
    parser.add_argument("--profile", help="Show one profile; otherwise list all profiles.")
    parser.add_argument("--check-runtime", action="store_true", help="Check local CLI flags without invoking a model.")
    args = parser.parse_args()
    root = resolve_root(args.root)
    config = load_config(root)
    try:
        names = [args.profile] if args.profile else list(profile_catalog(config))
        rows = [resolve_execution(config, profile_name=name) for name in names]
        if args.check_runtime:
            for row in rows:
                row["runtime_check"] = check_runtime(row, root)
        print(json.dumps(rows, indent=2))
        return int(any(not row.get("runtime_check", {"ok": True})["ok"] for row in rows))
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
