import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "scaffold_workspace.py"
PACKAGE_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "package_release.py"
AUDIT_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_release.py"


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
            self.assertTrue((destination / "hub" / "automations.md").exists())
            self.assertTrue((destination / "hub" / "scripts" / "preflight_capabilities.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "sync_workspace.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "memory_index_refresh.py").exists())
            self.assertTrue((destination / "hub" / "scripts" / "state_digest.py").exists())
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
            (work_item / "next-actions.md").write_text("- BLOCKED until approval to send.\n", encoding="utf-8")
            remote_upload = Path(tmpdir) / "remote-upload.txt"
            remote_upload.write_text("remote evidence", encoding="utf-8")

            commands = [
                [sys.executable, "hub/scripts/preflight_capabilities.py", "--root", "."],
                [sys.executable, "hub/scripts/sync_workspace.py", "--root", "."],
                [sys.executable, "hub/scripts/memory_index_refresh.py", "--root", ".", "--write", "--validate"],
                [sys.executable, "hub/scripts/state_digest.py", "--root", "."],
                [sys.executable, "hub/scripts/package_gate.py", "--root", ".", "--work-item", "work-items/case001"],
                [sys.executable, "hub/scripts/install_automations.py", "--root", ".", "--out", ".operator-automations"],
                [sys.executable, "hub/scripts/task_draft.py", "--root", ".", "--work-item", "work-items/case001", "--assignee", "Alex"],
                [sys.executable, "hub/scripts/backup_verify.py", "--root", ".", "--write-report"],
                [sys.executable, "hub/scripts/export_runtime_adapters.py", "--root", "."],
                [sys.executable, "hub/scripts/run_automation.py", "--root", ".", "--automation-id", "morning-control-panel"],
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
