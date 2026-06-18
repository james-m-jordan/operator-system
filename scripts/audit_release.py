#!/usr/bin/env python3
"""Audit the operator-system starter kit against release requirements."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PACKAGE_ROOT / "config" / "org.example.json"
SCAFFOLD_SCRIPT = PACKAGE_ROOT / "scripts" / "scaffold_workspace.py"
PACKAGE_SCRIPT = PACKAGE_ROOT / "scripts" / "package_release.py"

REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "BLUEPRINT.md",
    "INSTALL.md",
    "MIGRATION.md",
    "RELEASE-CHECKLIST.md",
    "COMPLETION-MATRIX.md",
    "config/org.example.json",
    "scripts/audit_release.py",
    "scripts/package_release.py",
    "scripts/scaffold_workspace.py",
    "templates/AGENTS.md",
    "templates/hub/automations.md",
    "templates/hub/automations/automation-manifest.json",
    "templates/work-items/README.md",
    "tests/test_scaffold_workspace.py",
]

REQUIRED_TEMPLATE_SCRIPTS = [
    "backup_transfer.py",
    "backup_verify.py",
    "chat_file_fetch.py",
    "chat_file_intake.py",
    "deliver_outbox.py",
    "export_runtime_adapters.py",
    "install_automations.py",
    "memory_index_refresh.py",
    "operator_common.py",
    "package_gate.py",
    "preflight_capabilities.py",
    "publish_status.py",
    "run_automation.py",
    "state_digest.py",
    "sync_workspace.py",
    "task_draft.py",
]

EXPECTED_AUTOMATIONS = [
    "morning-control-panel",
    "chat-intake-action-turn",
    "external-feed-digest",
    "opportunity-planning-refresh",
    "system-review-loop",
    "operations-checklist-scan",
    "workspace-backup",
    "receipt-packet-assembly",
    "chat-file-intake",
]

FORBIDDEN_GENERATED_TERMS = [
    "{{",
    "}}",
    "Jordan Lab",
    "biology",
    "team-projects",
    "proj###",
    "trainee",
    "lia-live",
]


def check(ok: bool, name: str, evidence: str, remediation: str = "") -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "evidence": evidence,
        "remediation": remediation,
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def audit_static_files() -> list[dict[str, Any]]:
    results = []
    for relative in REQUIRED_FILES:
        path = PACKAGE_ROOT / relative
        results.append(check(path.is_file(), f"required file: {relative}", relative, "Add the missing release artifact."))
    for script in REQUIRED_TEMPLATE_SCRIPTS:
        path = PACKAGE_ROOT / "templates" / "hub" / "scripts" / script
        results.append(check(path.is_file(), f"generated helper script: {script}", path.relative_to(PACKAGE_ROOT).as_posix()))
    return results


def audit_config() -> list[dict[str, Any]]:
    results = []
    config = load_json(CONFIG_PATH)
    for key in ["org_name", "workspace_name", "hub_root", "work_item_root", "knowledge_base_root"]:
        results.append(check(key in config, f"config key: {key}", "config/org.example.json"))
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    results.append(check(bool(runtime.get("publisher_targets")), "runtime publisher targets configured", "runtime.publisher_targets"))
    backup = config.get("backup", {}) if isinstance(config.get("backup"), dict) else {}
    transfer = backup.get("transfer", {}) if isinstance(backup.get("transfer"), dict) else {}
    results.append(check(bool(transfer.get("method")) and bool(transfer.get("destination")), "backup transfer configured", "backup.transfer"))
    file_sources = config.get("file_sources", {}) if isinstance(config.get("file_sources"), dict) else {}
    chat = file_sources.get("chat", {}) if isinstance(file_sources.get("chat"), dict) else {}
    providers = chat.get("providers", {}) if isinstance(chat.get("providers"), dict) else {}
    results.append(check({"direct-url", "slack", "command"}.issubset(set(providers)), "chat file providers configured", "file_sources.chat.providers"))
    return results


def audit_automation_manifest() -> list[dict[str, Any]]:
    manifest_path = PACKAGE_ROOT / "templates" / "hub" / "automations" / "automation-manifest.json"
    manifest = load_json(manifest_path)
    found = [item.get("id") for item in manifest.get("automations", []) if isinstance(item, dict)]
    results = []
    for automation_id in EXPECTED_AUTOMATIONS:
        results.append(check(automation_id in found, f"automation manifest includes {automation_id}", "templates/hub/automations/automation-manifest.json"))
    prompt_root = PACKAGE_ROOT / "templates" / "hub" / "automations"
    for item in manifest.get("automations", []):
        if not isinstance(item, dict):
            continue
        prompt_file = item.get("prompt_file", "")
        prompt_path = prompt_root / str(prompt_file)
        results.append(check(prompt_path.is_file(), f"automation prompt exists for {item.get('id')}", prompt_path.relative_to(PACKAGE_ROOT).as_posix()))
    return results


def audit_generated_workspace() -> list[dict[str, Any]]:
    results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        destination = Path(tmpdir) / "workspace"
        scaffold = run([sys.executable, str(SCAFFOLD_SCRIPT), "--config", str(CONFIG_PATH), "--out", str(destination), "--force"], PACKAGE_ROOT)
        scaffold_evidence = "scaffolded temporary workspace" if scaffold.returncode == 0 else scaffold.stderr.strip()
        results.append(check(scaffold.returncode == 0, "scaffold command succeeds", scaffold_evidence))
        if scaffold.returncode != 0:
            return results
        required_generated = [
            "AGENTS.md",
            "hub/MEMORY/LANDMARKS.md",
            "hub/MEMORY/state-digest.md",
            "hub/MEMORY/capabilities.json",
            "hub/automations/automation-manifest.json",
            "hub/scripts/preflight_capabilities.py",
            "hub/scripts/chat_file_fetch.py",
            "hub/scripts/deliver_outbox.py",
            "work-items/README.md",
            "knowledge-base/README.md",
        ]
        for relative in required_generated:
            results.append(check((destination / relative).exists(), f"generated path: {relative}", relative))
        offenders: list[str] = []
        for path in destination.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for term in FORBIDDEN_GENERATED_TERMS:
                if term in text:
                    offenders.append(f"{path.relative_to(destination).as_posix()} contains {term}")
        results.append(check(not offenders, "generated workspace is organization-neutral", "; ".join(offenders) or "no forbidden generated terms"))
    return results


def audit_release_archive() -> list[dict[str, Any]]:
    results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        result = run([sys.executable, str(PACKAGE_SCRIPT), "--version", "audit", "--out", str(out)], PACKAGE_ROOT)
        archive_evidence = "operator-system-starter-audit.tar.gz" if result.returncode == 0 else result.stderr.strip()
        results.append(check(result.returncode == 0, "release archive builds", archive_evidence))
        manifest_path = out / "operator-system-starter-audit.manifest.json"
        archive_path = out / "operator-system-starter-audit.tar.gz"
        results.append(check(manifest_path.is_file(), "release manifest exists", manifest_path.name))
        results.append(check(archive_path.is_file(), "release archive exists", archive_path.name))
        if manifest_path.is_file():
            manifest = load_json(manifest_path)
            file_paths = {item.get("path") for item in manifest.get("files", []) if isinstance(item, dict)}
            results.append(check(manifest.get("file_count", 0) >= 40, "release manifest has expected breadth", f"file_count={manifest.get('file_count')}"))
            results.append(check("templates/hub/scripts/chat_file_fetch.py" in file_paths, "release includes chat fetch helper", "manifest files"))
            results.append(check("scripts/audit_release.py" in file_paths, "release includes audit helper", "manifest files"))
            results.append(check("LICENSE" in file_paths, "release includes license", "manifest files"))
            vcs_paths = sorted(path for path in file_paths if isinstance(path, str) and (path == ".git" or path.startswith(".git/")))
            results.append(check(not vcs_paths, "release excludes git metadata", "; ".join(vcs_paths) or "manifest files"))
    return results


def audit_all() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    results.extend(audit_static_files())
    results.extend(audit_config())
    results.extend(audit_automation_manifest())
    results.extend(audit_generated_workspace())
    results.extend(audit_release_archive())
    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    status = "PASS" if report["ok"] else "BLOCKED"
    lines = [
        "# Operator System Completion Matrix",
        "",
        f"- Audit result: **{status}**",
        f"- Checks passed: {report['passed']}",
        f"- Checks failed: {report['failed']}",
        "",
        "## Matrix",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for item in report["results"]:
        status = "PASS" if item["ok"] else "FAIL"
        evidence = str(item.get("evidence", "")).replace("\n", " ")[:240]
        lines.append(f"| {item['name']} | {status} | `{evidence}` |")
    lines.extend(
        [
            "",
            "## Remaining Work",
            "",
        ]
    )
    failed = [item for item in report["results"] if not item["ok"]]
    if failed:
        for item in failed:
            remediation = item.get("remediation") or "Inspect the failed check and update the distribution."
            lines.append(f"- {item['name']}: {remediation}")
    else:
        lines.append("- No release-audit failures. Provider-specific integrations can still be added as optional adapters.")
    lines.append("")
    lines.append("Regenerate with:")
    lines.append("")
    lines.append("```bash")
    lines.append("python3 scripts/audit_release.py --write COMPLETION-MATRIX.md")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--write", default="", help="Write Markdown completion matrix.")
    args = parser.parse_args()
    report = audit_all()
    if args.write:
        target = Path(args.write)
        if not target.is_absolute():
            target = PACKAGE_ROOT / target
        target.write_text(render_markdown(report), encoding="utf-8")
        print(target)
    if args.json or not args.write:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
