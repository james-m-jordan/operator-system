import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "scaffold_workspace.py"
PACKAGE_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "package_release.py"
AUDIT_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_release.py"
UPGRADE_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "upgrade_workspace.py"
TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"


def load_scaffold_module():
    spec = importlib.util.spec_from_file_location("scaffold_workspace", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ScaffoldWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.module = load_scaffold_module()
        self.config = {
            "org_name": "Acme Operators",
            "workspace_name": "acme-ops-live",
            "admin_name": "Alex Admin",
            "timezone": "America/New_York",
            "primary_status_channel": "#operator-agent",
            "intake_channel": "#requests",
            "work_item_root": "work-items",
            "knowledge_base_root": "knowledge-base",
            "hub_root": "hub",
            "connectors": {
                "chat": "slack",
                "email": "gmail",
                "calendar": "google-calendar",
                "tasks": "github",
            },
            "file_sources": {
                "chat": {
                    "default_provider": "direct-url",
                    "providers": {
                        "direct-url": {"type": "direct-url"},
                        "slack": {"type": "slack-web-api", "token_env": "OPERATOR_SLACK_FILE_TOKEN"},
                    },
                },
            },
            "backup": {
                "required_paths": ["AGENTS.md", "hub", "work-items", "knowledge-base"],
                "exclude": [".DS_Store", "__pycache__/", ".pytest_cache/", "local-private/"],
                "transfer": {
                    "method": "local-copy",
                    "destination": "local-private/backups/latest",
                },
            },
            "runtime": {
                "adapter_output": ".operator-runtime",
                "outbox_root": "hub/MEMORY/outbox",
                "run_root": "hub/MEMORY/automation-runs",
                "scheduler_targets": ["cron", "github-actions"],
                "publisher_targets": {
                    "status": {
                        "type": "markdown-outbox",
                        "channel": "#operator-agent",
                        "delivery": {
                            "type": "slack-webhook",
                            "url_env": "OPERATOR_STATUS_WEBHOOK_URL",
                        },
                    }
                },
            },
            "automation_schedules": {
                "morning-control-panel": {
                    "enabled": True,
                    "cron": "0 8 * * 1-5",
                    "timezone": "America/New_York",
                },
                "chat-intake-action-turn": {
                    "enabled": True,
                    "cron": "*/30 * * * 1-5",
                    "timezone": "America/New_York",
                },
            },
        }

    def test_scaffold_renders_core_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)

            self.assertTrue((destination / "AGENTS.md").exists())
            self.assertTrue((destination / "hub" / "MEMORY" / "LANDMARKS.md").exists())
            self.assertTrue((destination / "hub" / "MEMORY" / "LESSONS.md").exists())
            self.assertTrue((destination / "hub" / "automations.md").exists())
            self.assertTrue((destination / "hub" / "scripts" / "preflight_capabilities.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "sync_workspace.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "memory_index_refresh.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "state_digest.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "memory_health.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "memory_compact.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "package_gate.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "install_automations.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "task_draft.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "backup_verify.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "backup_transfer.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "chat_file_fetch.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "chat_file_intake.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "run_automation.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "publish_status.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "deliver_outbox.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "export_runtime_adapters.py").exists())
            self.assertTrue((destination / "hub" / "automations" / "automation-manifest.json").exists())
            self.assertTrue((destination / "work-items" / "README.md").exists())
            self.assertTrue((destination / "knowledge-base" / "README.md").exists())
            self.assertTrue((destination / "local-private").is_dir())

            agents = (destination / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Acme Operators", agents)
            self.assertIn("acme-ops-live", agents)
            self.assertNotIn("Jordan Lab", agents)
            self.assertNotIn("biology", agents.lower())

            capabilities = json.loads((destination / "hub" / "MEMORY" / "capabilities.json").read_text())
            self.assertFalse(capabilities["checks"]["chat"]["ok"])
            self.assertIn("git_push_path", capabilities["checks"])

    def test_generated_helper_chain_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)

            work_item = destination / "work-items" / "case001"
            (work_item / "source").mkdir(parents=True)
            (work_item / "metadata").mkdir()
            (work_item / "README.md").write_text(
                "# Case 001\n\nOwner: Alex\n\nRequest: summarize the packet.\n\nDecision boundary: draft only.\n",
                encoding="utf-8",
            )
            (work_item / "source" / "request.txt").write_text("source", encoding="utf-8")
            (work_item / "metadata" / "map.csv").write_text("file,meaning\nrequest.txt,source request\n", encoding="utf-8")
            (work_item / "next-actions.md").write_text(
                "- BLOCKED until approval to send.\n"
                "- BLOCKED until approval to send.\n"
                "- The summary needs data from Alex.\n",
                encoding="utf-8",
            )
            remote_upload = Path(tmpdir) / "remote-upload.txt"
            remote_upload.write_text("remote evidence", encoding="utf-8")

            commands = [
                [sys.executable, "hub/scripts/config_check.py", "--root", "."],
                [sys.executable, "hub/scripts/retention_sweep.py", "--root", "."],
                [sys.executable, "hub/scripts/preflight_capabilities.py", "--root", "."],
                [sys.executable, "hub/scripts/sync_workspace.py", "--root", "."],
                [sys.executable, "hub/scripts/memory_index_refresh.py", "--root", ".", "--write", "--validate"],
                [sys.executable, "hub/scripts/state_digest.py", "--root", "."],
                [sys.executable, "hub/scripts/memory_health.py", "--root", ".", "--write"],
                [sys.executable, "hub/scripts/memory_compact.py", "--root", "."],
                [sys.executable, "hub/scripts/package_gate.py", "--root", ".", "--work-item", "work-items/case001"],
                [sys.executable, "hub/scripts/install_automations.py", "--root", ".", "--out", ".operator-automations"],
                [sys.executable, "hub/scripts/task_draft.py", "--root", ".", "--work-item", "work-items/case001", "--assignee", "Alex"],
                [sys.executable, "hub/scripts/backup_verify.py", "--root", ".", "--write-report"],
                [sys.executable, "hub/scripts/export_runtime_adapters.py", "--root", "."],
                [sys.executable, "hub/scripts/run_automation.py", "--root", ".", "--automation-id", "morning-control-panel"],
                [sys.executable, "hub/scripts/run_close.py", "--root", ".", "--latest", "--outcome", "success", "--improvement", "lesson", "--improvement-ref", "hub/MEMORY/LESSONS.md"],
                [sys.executable, "hub/scripts/lesson_add.py", "--root", ".", "--rule", "Run the package gate before any analysis.", "--evidence", "hub/MEMORY/README.md"],
                [sys.executable, "hub/scripts/wiki_compile.py", "--root", "."],
                [sys.executable, "hub/scripts/memory_search.py", "--root", ".", "--query", "case001"],
                [sys.executable, "hub/scripts/memory_health.py", "--root", ".", "--write"],
                [sys.executable, "hub/scripts/publish_status.py", "--root", ".", "--publisher", "status", "--message", "Ready"],
                [sys.executable, "hub/scripts/deliver_outbox.py", "--root", ".", "--publisher", "status", "--latest"],
                [sys.executable, "hub/scripts/backup_transfer.py", "--root", ".", "--destination", "local-private/backup-copy", "--execute", "--write-report"],
                [sys.executable, "hub/scripts/backup_transfer.py", "--root", ".", "--method", "rsync", "--destination", "backup.example:/srv/operator", "--write-report"],
                [sys.executable, "hub/scripts/chat_file_fetch.py", "--root", ".", "--provider", "direct-url", "--url", remote_upload.as_uri(), "--output", "local-private/chat-downloads/fetched-upload.txt"],
            ]
            for command in commands:
                result = subprocess.run(command, cwd=destination, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, msg=f"{command} failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

            index = json.loads((destination / "hub" / "MEMORY" / "indexes" / "work-item-index.json").read_text())
            self.assertEqual(index[0]["id"], "case001")
            self.assertEqual(index[0]["package_status"], "ready_for_work")
            digest = (destination / "hub" / "MEMORY" / "state-digest.md").read_text(encoding="utf-8")
            self.assertIn("Case 001", digest)
            self.assertIn("Memory Health", digest)
            health = json.loads((destination / "hub" / "MEMORY" / "indexes" / "memory-health.json").read_text(encoding="utf-8"))
            self.assertTrue(health["ok"], msg=health)
            unclosed = next(check for check in health["checks"] if check["name"] == "unclosed_automation_runs")
            self.assertEqual(unclosed["value"], 0)
            history = (destination / "hub" / "MEMORY" / "indexes" / "memory-health-history.jsonl").read_text(encoding="utf-8")
            self.assertGreaterEqual(len(history.strip().splitlines()), 2)
            blocker_index = json.loads((destination / "hub" / "MEMORY" / "indexes" / "blocker-index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(blocker_index), 2)
            self.assertEqual(blocker_index[0]["confidence"], "explicit")
            self.assertEqual(blocker_index[1]["confidence"], "inferred")
            close_files = list((destination / "hub" / "MEMORY" / "automation-runs").glob("*/close.json"))
            self.assertEqual(len(close_files), 1)
            close = json.loads(close_files[0].read_text(encoding="utf-8"))
            self.assertEqual(close["outcome"], "success")
            self.assertEqual(close["improvement"], "lesson")
            run_packet = next((destination / "hub" / "MEMORY" / "automation-runs").glob("*/run.md")).read_text(encoding="utf-8")
            self.assertIn("## Active Lessons", run_packet)
            self.assertIn("## Required Closeout", run_packet)
            wiki = (destination / "hub" / "wiki" / "overview.md").read_text(encoding="utf-8")
            self.assertIn("Active Lessons", wiki)
            self.assertIn("case001", wiki)
            installed = (destination / ".operator-automations" / "morning-control-panel" / "automation.md").read_text(encoding="utf-8")
            self.assertIn("Standard Ratchet", installed)
            lessons = (destination / "hub" / "MEMORY" / "LESSONS.md").read_text(encoding="utf-8")
            self.assertIn("Run the package gate before any analysis.", lessons)
            self.assertTrue((destination / ".operator-automations" / "morning-control-panel" / "automation.json").exists())
            self.assertTrue((destination / "hub" / "MEMORY" / "task-drafts").is_dir())
            self.assertTrue((destination / "hub" / "MEMORY" / "backups").is_dir())
            self.assertTrue((destination / ".operator-runtime" / "cron" / "operator-system.crontab").exists())
            self.assertTrue((destination / ".operator-runtime" / "github-actions" / "operator-automations.yml").exists())
            runtime_export = json.loads((destination / ".operator-runtime" / "runtime-export.json").read_text(encoding="utf-8"))
            self.assertIn("morning-control-panel", runtime_export["enabled_automations"])
            actions = (destination / ".operator-runtime" / "github-actions" / "operator-automations.yml").read_text(encoding="utf-8")
            self.assertIn("github.event.schedule == '0 8 * * 1-5'", actions)
            self.assertTrue(any((destination / "hub" / "MEMORY" / "automation-runs").glob("*/run.md")))
            self.assertTrue(any((destination / "hub" / "MEMORY" / "outbox" / "status").glob("*.json")))
            self.assertTrue(any((destination / "hub" / "MEMORY" / "outbox-deliveries" / "status").glob("*.json")))
            self.assertTrue((destination / "local-private" / "backup-copy" / "AGENTS.md").exists())
            self.assertTrue(any((destination / "hub" / "MEMORY" / "backups").glob("backup-transfer-*.md")))
            fetched = destination / "local-private" / "chat-downloads" / "fetched-upload.txt"
            self.assertEqual(fetched.read_text(encoding="utf-8"), "remote evidence")
            self.assertTrue(fetched.with_suffix(".txt.metadata.json").exists())

    def test_chat_file_intake_copies_file_and_records_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            source = Path(tmpdir) / "upload.txt"
            source.write_text("uploaded evidence", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "hub/scripts/chat_file_intake.py",
                    "--root",
                    ".",
                    "--work-item",
                    "case003",
                    "--source-file",
                    str(source),
                    "--source-url",
                    "https://chat.example/files/1",
                    "--metadata",
                    "requester=Alex",
                ],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            copied = destination / "work-items" / "case003" / "source" / "chat-uploads" / "upload.txt"
            metadata = destination / "work-items" / "case003" / "metadata" / "chat-file-intake.json"
            self.assertEqual(copied.read_text(encoding="utf-8"), "uploaded evidence")
            payload = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["source_url"], "https://chat.example/files/1")
            self.assertEqual(payload[0]["extra"]["requester"], "Alex")

    def test_memory_compact_rotates_old_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)

            log_path = destination / "hub" / "MEMORY" / "agent-action-log.md"
            entries = [f"- 2024-01-{day:02d} - agent - scope - action {day} - paths - next" for day in range(1, 11)]
            entries.insert(3, "- undated note that should never be archived")
            log_path.write_text(
                "# Agent Action Log\n\nFormat notes.\n\n## Log\n\n" + "\n".join(entries) + "\n",
                encoding="utf-8",
            )

            dry_run = subprocess.run(
                [sys.executable, "hub/scripts/memory_compact.py", "--root", ".", "--keep", "4"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(dry_run.returncode, 0, msg=dry_run.stderr)
            self.assertIn("Dry run", dry_run.stdout)
            self.assertIn("## Log", log_path.read_text(encoding="utf-8"))
            self.assertIn("action 1", log_path.read_text(encoding="utf-8"))

            result = subprocess.run(
                [sys.executable, "hub/scripts/memory_compact.py", "--root", ".", "--keep", "4", "--execute"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            rotated = log_path.read_text(encoding="utf-8")
            self.assertIn("undated note that should never be archived", rotated)
            self.assertIn("action 10", rotated)
            self.assertIn("action 7", rotated)
            self.assertNotIn("action 1 ", rotated)
            archive = destination / "hub" / "MEMORY" / "archive" / "action-log-2024.md"
            archived = archive.read_text(encoding="utf-8")
            self.assertIn("action 1", archived)
            self.assertIn("action 6", archived)
            self.assertNotIn("action 7", archived)
            self.assertNotIn("undated note", archived)

    def test_ops_startup_runs_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            result = subprocess.run(
                [sys.executable, "hub/scripts/ops.py", "startup"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
            self.assertTrue((destination / "hub" / "MEMORY" / "indexes" / "memory-health.json").exists())
            self.assertTrue((destination / "hub" / "MEMORY" / "state-digest.md").exists())

    def test_config_check_flags_bad_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            config_path = destination / "hub" / "config" / "org.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["automation_schedules"]["morning-control-panel"]["cron"] = "not a cron"
            config["memory_budgets"] = {"landmarks_max_lines": -3}
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, "hub/scripts/config_check.py", "--root", ".", "--json"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertTrue(any("cron" in error for error in payload["errors"]))
            self.assertTrue(any("landmarks_max_lines" in error for error in payload["errors"]))

    def test_retention_sweep_archives_old_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            runs = destination / "hub" / "MEMORY" / "automation-runs"
            old_run = runs / "20200101T000000Z-morning-control-panel"
            old_run.mkdir(parents=True)
            (old_run / "run.json").write_text("{}", encoding="utf-8")
            fresh_run = runs / "20990101T000000Z-morning-control-panel"
            fresh_run.mkdir(parents=True)
            (fresh_run / "run.json").write_text("{}", encoding="utf-8")

            dry = subprocess.run(
                [sys.executable, "hub/scripts/retention_sweep.py", "--root", "."],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, msg=dry.stderr)
            self.assertIn("Dry run", dry.stdout)
            self.assertTrue(old_run.exists())

            result = subprocess.run(
                [sys.executable, "hub/scripts/retention_sweep.py", "--root", ".", "--execute"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertFalse(old_run.exists())
            self.assertTrue(fresh_run.exists())
            retired = destination / "hub" / "MEMORY" / "archive" / "retired" / "automation-runs" / old_run.name
            self.assertTrue(retired.exists())

    def test_memory_health_strict_fails_over_budget(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            config_path = destination / "hub" / "config" / "org.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["memory_budgets"] = {"lessons_max_lines": 1}
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

            result = subprocess.run(
                [sys.executable, "hub/scripts/memory_health.py", "--root", ".", "--strict"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("lessons_lines", result.stdout)

    def test_state_digest_marks_overdue_automation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            run_dir = destination / "hub" / "MEMORY" / "automation-runs" / "20200101T000000Z-morning-control-panel"
            run_dir.mkdir(parents=True)
            (run_dir / "run.json").write_text(
                json.dumps({"automation_id": "morning-control-panel", "created_utc": "2020-01-01T00:00:00Z"}),
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "hub/scripts/state_digest.py", "--root", "."],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            digest = (destination / "hub" / "MEMORY" / "state-digest.md").read_text(encoding="utf-8")
            self.assertIn("OVERDUE", digest)

    def test_deliver_outbox_command_timeout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            config_path = destination / "hub" / "config" / "org.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["runtime"]["publisher_targets"]["status"]["delivery"] = {
                "type": "command",
                "command": [sys.executable, "-c", "import time; time.sleep(10)"],
                "timeout_seconds": 1,
            }
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

            publish = subprocess.run(
                [sys.executable, "hub/scripts/publish_status.py", "--root", ".", "--publisher", "status", "--message", "Timeout test"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(publish.returncode, 0, msg=publish.stderr)
            result = subprocess.run(
                [sys.executable, "hub/scripts/deliver_outbox.py", "--root", ".", "--publisher", "status", "--latest", "--execute"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 124)
            receipt = next((destination / "hub" / "MEMORY" / "outbox-deliveries" / "status").glob("*.json"))
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertIn("timed out", payload["detail"])

    def test_lesson_add_deduplicates_and_prunes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            lessons_path = destination / "hub" / "MEMORY" / "LESSONS.md"

            def run_lesson(*extra):
                return subprocess.run(
                    [sys.executable, "hub/scripts/lesson_add.py", "--root", ".", *extra],
                    cwd=destination,
                    capture_output=True,
                    text=True,
                    check=False,
                )

            first = run_lesson("--rule", "Verify webhook delivery receipts after every send.", "--evidence", "hub/MEMORY/comms.md")
            self.assertEqual(first.returncode, 0, msg=first.stderr)
            self.assertIn("added new lesson", first.stdout)

            second = run_lesson("--rule", "Verify webhook delivery receipts after each send.")
            self.assertEqual(second.returncode, 0, msg=second.stderr)
            self.assertIn("re-confirmed existing lesson (hits: 2)", second.stdout)
            text = lessons_path.read_text(encoding="utf-8")
            self.assertEqual(text.count("Verify webhook delivery receipts"), 1)
            self.assertIn("hits: 2", text)

            pruned = run_lesson("--prune", "webhook delivery receipts")
            self.assertEqual(pruned.returncode, 0, msg=pruned.stderr)
            self.assertNotIn("webhook delivery receipts", lessons_path.read_text(encoding="utf-8"))

    def test_run_automation_invoke_records_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            config = dict(self.config)
            config["runtime"] = dict(self.config["runtime"])
            config["runtime"]["agent_command"] = [sys.executable, "-c", "import sys; print('packet:', sys.argv[1])", "{packet}"]
            self.module.scaffold(config, destination)

            result = subprocess.run(
                [sys.executable, "hub/scripts/run_automation.py", "--root", ".", "--automation-id", "morning-control-panel", "--invoke"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            invoke_files = list((destination / "hub" / "MEMORY" / "automation-runs").glob("*/invoke.json"))
            self.assertEqual(len(invoke_files), 1)
            invoke = json.loads(invoke_files[0].read_text(encoding="utf-8"))
            self.assertEqual(invoke["returncode"], 0)
            self.assertIn("packet:", invoke["output_tail"])

    def test_sync_workspace_dry_run_then_execute(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)

            def git(cwd, *args):
                result = subprocess.run(
                    ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", *args],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, msg=f"git {args} failed: {result.stderr}")
                return result.stdout.strip()

            origin = Path(tmpdir) / "origin"
            origin.mkdir()
            git(origin, "init", "-b", "main")
            (origin / "file.txt").write_text("one\n", encoding="utf-8")
            git(origin, "add", "file.txt")
            git(origin, "commit", "-m", "first")
            clone = destination / "work-items" / "repo1"
            git(destination, "clone", str(origin), str(clone))
            (origin / "file.txt").write_text("two\n", encoding="utf-8")
            git(origin, "commit", "-am", "second")

            dry = subprocess.run(
                [sys.executable, "hub/scripts/sync_workspace.py", "--root", "."],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, msg=dry.stderr)
            self.assertIn("Dry run: some repos need syncing", dry.stdout)
            self.assertEqual((clone / "file.txt").read_text(encoding="utf-8"), "one\n")

            executed = subprocess.run(
                [sys.executable, "hub/scripts/sync_workspace.py", "--root", ".", "--execute"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(executed.returncode, 0, msg=executed.stderr)
            self.assertEqual((clone / "file.txt").read_text(encoding="utf-8"), "two\n")

    def test_lesson_pack_export_import_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_ws = Path(tmpdir) / "source"
            target_ws = Path(tmpdir) / "target"
            self.module.scaffold(self.config, source_ws)
            self.module.scaffold(self.config, target_ws)

            for _ in range(3):
                subprocess.run(
                    [sys.executable, "hub/scripts/lesson_add.py", "--root", ".", "--rule", "Escalate ambiguous approvals to the owner.", "--evidence", "hub/MEMORY/comms.md"],
                    cwd=source_ws,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            subprocess.run(
                [sys.executable, "hub/scripts/lesson_add.py", "--root", ".", "--rule", "Low-signal one-off note.", "--evidence", "x"],
                cwd=source_ws,
                capture_output=True,
                text=True,
                check=False,
            )

            pack_path = Path(tmpdir) / "pack.json"
            export = subprocess.run(
                [sys.executable, "hub/scripts/lesson_pack.py", "export", "--root", ".", "--min-hits", "3", "--name", "ops-wisdom", "--out", str(pack_path)],
                cwd=source_ws,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(export.returncode, 0, msg=export.stderr)
            pack = json.loads(pack_path.read_text(encoding="utf-8"))
            self.assertEqual(pack["source"], "anonymous")
            rules = [lesson["rule"] for lesson in pack["lessons"]]
            self.assertIn("Escalate ambiguous approvals to the owner.", rules)
            self.assertNotIn("Low-signal one-off note.", rules)
            self.assertTrue(all(lesson["evidence"] == "" for lesson in pack["lessons"]))

            dry = subprocess.run(
                [sys.executable, "hub/scripts/lesson_pack.py", "import", "--root", ".", "--pack", str(pack_path)],
                cwd=target_ws,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(dry.returncode, 0, msg=dry.stderr)
            self.assertIn("Dry run", dry.stdout)
            self.assertNotIn("Escalate ambiguous approvals", (target_ws / "hub" / "MEMORY" / "LESSONS.md").read_text(encoding="utf-8"))

            merged = subprocess.run(
                [sys.executable, "hub/scripts/lesson_pack.py", "import", "--root", ".", "--pack", str(pack_path), "--execute"],
                cwd=target_ws,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(merged.returncode, 0, msg=merged.stderr)
            lessons = (target_ws / "hub" / "MEMORY" / "LESSONS.md").read_text(encoding="utf-8")
            self.assertIn("Escalate ambiguous approvals to the owner.", lessons)
            self.assertIn("pack:ops-wisdom", lessons)

    def test_close_chain_verifies_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            for automation_id in ("morning-control-panel", "system-review-loop"):
                subprocess.run(
                    [sys.executable, "hub/scripts/run_automation.py", "--root", ".", "--automation-id", automation_id],
                    cwd=destination,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                close = subprocess.run(
                    [sys.executable, "hub/scripts/run_close.py", "--root", ".", "--latest", "--outcome", "success", "--improvement", "pruning"],
                    cwd=destination,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(close.returncode, 0, msg=close.stderr)

            chain_path = destination / "hub" / "MEMORY" / "indexes" / "close-chain.jsonl"
            entries = [json.loads(line) for line in chain_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[1]["prev_hash"], entries[0]["hash"])

            verify = subprocess.run(
                [sys.executable, "hub/scripts/run_close.py", "--root", ".", "--verify-chain"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, msg=verify.stdout)
            self.assertIn("Chain OK: 2", verify.stdout)

            tampered = chain_path.read_text(encoding="utf-8").replace('"outcome": "success"', '"outcome": "failure"', 1)
            chain_path.write_text(tampered, encoding="utf-8")
            broken = subprocess.run(
                [sys.executable, "hub/scripts/run_close.py", "--root", ".", "--verify-chain"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(broken.returncode, 1)
            self.assertIn("BROKEN", broken.stdout)

    def test_operator_report_summarizes_activity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            subprocess.run(
                [sys.executable, "hub/scripts/run_automation.py", "--root", ".", "--automation-id", "morning-control-panel"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            subprocess.run(
                [sys.executable, "hub/scripts/run_close.py", "--root", ".", "--latest", "--outcome", "success", "--lesson", "Report test lesson about verifying digests."],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            result = subprocess.run(
                [sys.executable, "hub/scripts/operator_report.py", "--root", ".", "--write"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            report = next((destination / "hub" / "MEMORY" / "reports").glob("operator-report-*.md")).read_text(encoding="utf-8")
            self.assertIn("Closed runs: **1**", report)
            self.assertIn("success: 1", report)
            self.assertIn("lesson: 1", report)
            self.assertIn("morning-control-panel", report)

    def test_memory_search_ranks_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            (destination / "hub" / "MEMORY" / "comms.md").write_text(
                "# Communication Memory\n\n- Decided to retire the zebra pipeline.\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, "hub/scripts/memory_search.py", "--root", ".", "--query", "zebra"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("comms.md", result.stdout)
            self.assertIn("zebra pipeline", result.stdout)

            empty = subprocess.run(
                [sys.executable, "hub/scripts/memory_search.py", "--root", ".", "--query", "nonexistentterm"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(empty.returncode, 0, msg=empty.stderr)
            self.assertIn("No matches", empty.stdout)

    def test_upgrade_workspace_applies_safe_updates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)

            kit = Path(tmpdir) / "kit"
            shutil.copytree(TEMPLATE_ROOT, kit / "templates")
            (kit / "templates" / "hub" / "scripts" / "new_helper.py").write_text("print('new helper')\n", encoding="utf-8")
            kit_script = kit / "templates" / "hub" / "scripts" / "state_digest.py"
            kit_script.write_text(kit_script.read_text(encoding="utf-8") + "\n# kit-improvement\n", encoding="utf-8")
            kit_agents = kit / "templates" / "AGENTS.md"
            kit_agents.write_text(kit_agents.read_text(encoding="utf-8") + "\nKit note.\n", encoding="utf-8")
            workspace_agents = destination / "AGENTS.md"
            workspace_agents.write_text(
                workspace_agents.read_text(encoding="utf-8") + "\nLocal customization.\n", encoding="utf-8"
            )

            dry_run = subprocess.run(
                [sys.executable, str(UPGRADE_SCRIPT_PATH), "--workspace", str(destination), "--kit-root", str(kit)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(dry_run.returncode, 0, msg=dry_run.stderr)
            self.assertIn("add: hub/scripts/new_helper.py", dry_run.stdout)
            self.assertIn("update: hub/scripts/state_digest.py", dry_run.stdout)
            self.assertIn("conflict: AGENTS.md", dry_run.stdout)
            self.assertFalse((destination / "hub" / "scripts" / "new_helper.py").exists())

            check = subprocess.run(
                [sys.executable, str(UPGRADE_SCRIPT_PATH), "--workspace", str(destination), "--kit-root", str(kit), "--check"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check.returncode, 1, msg=check.stdout)
            marker = json.loads((destination / "hub" / "MEMORY" / "indexes" / "kit-update.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(marker["adds"], 1)
            self.assertGreaterEqual(marker["updates"], 1)

            result = subprocess.run(
                [sys.executable, str(UPGRADE_SCRIPT_PATH), "--workspace", str(destination), "--kit-root", str(kit), "--execute"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue((destination / "hub" / "scripts" / "new_helper.py").exists())
            self.assertIn("# kit-improvement", (destination / "hub" / "scripts" / "state_digest.py").read_text(encoding="utf-8"))
            upgraded_agents = workspace_agents.read_text(encoding="utf-8")
            self.assertIn("Local customization.", upgraded_agents)
            self.assertNotIn("Kit note.", upgraded_agents)
            manifest = json.loads((destination / "hub" / "config" / "template-manifest.json").read_text(encoding="utf-8"))
            self.assertIn("hub/scripts/new_helper.py", manifest["files"])
            self.assertFalse((destination / "hub" / "MEMORY" / "indexes" / "kit-update.json").exists())

    def test_package_gate_blocks_incomplete_work_item(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            self.module.scaffold(self.config, destination)
            work_item = destination / "work-items" / "case002"
            work_item.mkdir(parents=True)
            (work_item / "README.md").write_text("# Case 002\n\nOwner: Alex\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, "hub/scripts/package_gate.py", "--root", ".", "--work-item", "work-items/case002", "--json"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])
            self.assertIn("source_files_present", payload["missing"])
            self.assertIn("metadata_present", payload["missing"])

            drafted = subprocess.run(
                [sys.executable, "hub/scripts/package_gate.py", "--root", ".", "--work-item", "work-items/case002", "--draft-task"],
                cwd=destination,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(drafted.returncode, 1)
            self.assertIn("Task draft created", drafted.stdout)
            self.assertTrue(any((destination / "hub" / "MEMORY" / "task-drafts").glob("*case002*")))

    def test_refuses_non_empty_destination_without_force(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "workspace"
            destination.mkdir()
            (destination / "existing.txt").write_text("keep", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                self.module.scaffold(self.config, destination)

    def test_config_validation_requires_core_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "bad.json"
            config_path.write_text(json.dumps({"org_name": "Missing Keys"}), encoding="utf-8")

            with self.assertRaises(ValueError):
                self.module.load_config(config_path)

    def test_package_release_builds_archive_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(PACKAGE_SCRIPT_PATH),
                    "--version",
                    "test",
                    "--out",
                    tmpdir,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            archive = Path(tmpdir) / "operator-system-starter-test.tar.gz"
            manifest_path = Path(tmpdir) / "operator-system-starter-test.manifest.json"
            self.assertTrue(archive.exists())
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["archive"], archive.name)
            self.assertGreater(manifest["file_count"], 10)
            file_paths = [item["path"] for item in manifest["files"]]
            self.assertIn("README.md", file_paths)
            self.assertIn("COMPLETION-MATRIX.md", file_paths)
            self.assertIn("scripts/audit_release.py", file_paths)

    def test_release_audit_passes(self):
        result = subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT_PATH), "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["failed"], 0)
        self.assertGreaterEqual(payload["passed"], 70)


if __name__ == "__main__":
    unittest.main()
