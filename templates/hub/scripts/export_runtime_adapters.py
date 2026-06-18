#!/usr/bin/env python3
"""Export scheduler and publisher adapter files for the generated workspace."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from operator_common import hub_dir, load_config, relpath, resolve_root, write_json, write_text


def load_manifest(root: Path, config: dict[str, object]) -> dict[str, object]:
    path = hub_dir(root, config) / "automations" / "automation-manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def enabled_schedules(config: dict[str, object], manifest: dict[str, object]) -> list[tuple[dict[str, object], dict[str, object]]]:
    schedules = config.get("automation_schedules", {}) if isinstance(config.get("automation_schedules"), dict) else {}
    output = []
    for automation in manifest.get("automations", []):
        schedule = schedules.get(automation["id"], {})
        if isinstance(schedule, dict) and schedule.get("enabled"):
            output.append((automation, schedule))
    return output


def job_id(value: object) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "-", str(value)).strip("-").lower() or "automation"


def render_crontab(root: Path, pairs: list[tuple[dict[str, object], dict[str, object]]]) -> str:
    lines = [
        "# Operator-system automation crontab",
        "# Review before installing with `crontab <file>`.",
        f"SHELL=/bin/bash",
        "",
    ]
    for automation, schedule in pairs:
        cron = schedule.get("cron", "")
        if not cron:
            continue
        command = (
            f"cd {shlex.quote(str(root))} && "
            f"python3 hub/scripts/run_automation.py --root . --automation-id {shlex.quote(str(automation['id']))}"
        )
        lines.append(f"# {automation['title']} ({automation['id']})")
        lines.append(f"{cron} {command}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_github_actions(pairs: list[tuple[dict[str, object], dict[str, object]]]) -> str:
    lines = [
        "name: Operator Automations",
        "",
        "on:",
        "  workflow_dispatch:",
        "  schedule:",
    ]
    cron_entries = []
    for _, schedule in pairs:
        cron = schedule.get("cron", "")
        if cron and cron not in cron_entries:
            cron_entries.append(cron)
    if cron_entries:
        for cron in cron_entries:
            lines.append(f"    - cron: '{cron}'")
    else:
        lines.append("    - cron: '0 8 * * 1'")
    lines.extend(
        [
            "",
            "jobs:",
        ]
    )
    if pairs:
        for automation, schedule in pairs:
            cron = schedule.get("cron", "")
            lines.extend(
                [
                    f"  {job_id(automation['id'])}:",
                    f"    if: github.event_name == 'workflow_dispatch' || github.event.schedule == '{cron}'",
                    "    runs-on: ubuntu-latest",
                    "    steps:",
                    "      - uses: actions/checkout@v4",
                    "      - uses: actions/setup-python@v5",
                    "        with:",
                    "          python-version: '3.x'",
                    "      - name: Create run packet",
                    "        run: |",
                    "          python3 hub/scripts/preflight_capabilities.py --root . || true",
                    f"          python3 hub/scripts/run_automation.py --root . --automation-id {automation['id']}",
                ]
            )
    else:
        lines.extend(
            [
                "  no-enabled-automations:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - run: echo 'No enabled automations configured.'",
            ]
        )
    return "\n".join(lines) + "\n"


def render_publishers(config: dict[str, object]) -> str:
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    publishers = runtime.get("publisher_targets", {}) if isinstance(runtime.get("publisher_targets"), dict) else {}
    lines = ["# Publisher Adapters", ""]
    if not publishers:
        lines.append("- No publisher targets configured.")
    for name, publisher in publishers.items():
        if not isinstance(publisher, dict):
            publisher = {"type": str(publisher)}
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"- Type: `{publisher.get('type', 'markdown-outbox')}`")
        if publisher.get("channel"):
            lines.append(f"- Channel: `{publisher['channel']}`")
        if publisher.get("destination"):
            lines.append(f"- Destination: `{publisher['destination']}`")
        delivery = publisher.get("delivery", {})
        if isinstance(delivery, dict) and delivery:
            lines.append(f"- Delivery type: `{delivery.get('type', 'noop')}`")
            if delivery.get("url_env"):
                lines.append(f"- URL environment variable: `{delivery['url_env']}`")
            if delivery.get("repo_env"):
                lines.append(f"- Repository environment variable: `{delivery['repo_env']}`")
        lines.append("")
        lines.append("Dry-run/write an outbox payload:")
        lines.append("")
        lines.append("```bash")
        lines.append(f"python3 hub/scripts/publish_status.py --root . --publisher {name} --message 'Status text here'")
        lines.append("```")
        lines.append("")
        lines.append("Dry-run delivery from the latest outbox item:")
        lines.append("")
        lines.append("```bash")
        lines.append(f"python3 hub/scripts/deliver_outbox.py --root . --publisher {name} --latest")
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def export(root: Path, out: Path) -> list[Path]:
    config = load_config(root)
    manifest = load_manifest(root, config)
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    scheduler_targets = runtime.get("scheduler_targets", ["cron", "github-actions"])
    if not isinstance(scheduler_targets, list):
        scheduler_targets = ["cron", "github-actions"]
    scheduler_targets = {str(target) for target in scheduler_targets}
    pairs = enabled_schedules(config, manifest)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    summary_lines = ["# Runtime Adapter Export", ""]
    publishers_path = out / "publishers.md"
    if "cron" in scheduler_targets:
        cron_path = out / "cron" / "operator-system.crontab"
        write_text(cron_path, render_crontab(root, pairs))
        written.append(cron_path)
        summary_lines.append(f"- Crontab: `{relpath(root, cron_path)}`")
    if "github-actions" in scheduler_targets:
        actions_path = out / "github-actions" / "operator-automations.yml"
        write_text(actions_path, render_github_actions(pairs))
        written.append(actions_path)
        summary_lines.append(f"- GitHub Actions workflow draft: `{relpath(root, actions_path)}`")
    write_text(publishers_path, render_publishers(config))
    written.append(publishers_path)
    summary = {
        "enabled_automations": [automation["id"] for automation, _ in pairs],
        "output": relpath(root, out),
        "scheduler_targets": sorted(scheduler_targets),
        "files": [relpath(root, path) for path in written],
    }
    write_json(out / "runtime-export.json", summary)
    summary_lines.insert(2, f"- Enabled automations: {', '.join(summary['enabled_automations']) or 'none'}")
    summary_lines.append(f"- Publisher notes: `{relpath(root, publishers_path)}`")
    summary_lines.extend(["", "Review generated files before installing them into a real scheduler.", ""])
    summary_path = out / "README.md"
    write_text(
        summary_path,
        "\n".join(summary_lines),
    )
    written.extend([summary_path, out / "runtime-export.json"])
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="", help="Workspace root.")
    parser.add_argument("--out", default="", help="Output directory. Defaults to runtime.adapter_output.")
    args = parser.parse_args()
    root = resolve_root(args.root)
    config = load_config(root)
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime"), dict) else {}
    out = Path(args.out or runtime.get("adapter_output", ".operator-runtime"))
    if not out.is_absolute():
        out = root / out
    written = export(root, out)
    print(f"Exported runtime adapters to {out}")
    for path in written:
        print(f"- {relpath(root, path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
