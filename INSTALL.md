# Operator System Install Guide

This package creates an organization-neutral operator workspace. It does not
install live credentials, send messages, or register schedulers automatically.

## 1. Prepare Config

Copy `config/org.example.json` and edit:

- `org_name`, `workspace_name`, `admin_name`, and `timezone`
- connector names under `connectors`
- `file_sources.chat.providers` for direct URL, Slack Web API, or custom command
  file-byte fetches
- `runtime.adapter_output`, `runtime.outbox_root`, and `runtime.run_root`
- `runtime.publisher_targets.<name>.delivery` for optional live delivery
- `automation_schedules` for the automations the organization should run
- `backup.required_paths`, `backup.exclude`, and `backup.transfer`

Keep private credentials outside the repo.

## 2. Scaffold Workspace

```bash
python3 scripts/scaffold_workspace.py --config config/org.example.json --out /path/to/workspace
cd /path/to/workspace
```

Run the startup helper chain:

```bash
python3 hub/scripts/preflight_capabilities.py --root .
python3 hub/scripts/sync_workspace.py --root .
python3 hub/scripts/memory_index_refresh.py --root . --write --validate
python3 hub/scripts/state_digest.py --root .
```

## 3. Install Automation Specs

```bash
python3 hub/scripts/install_automations.py --root . --out .operator-automations
```

This writes prompt/spec bundles for review. The generated files are runtime
inputs, not proof that a connector has been configured.

## 4. Export Runtime Adapters

```bash
python3 hub/scripts/export_runtime_adapters.py --root .
```

Review `.operator-runtime/`:

- `cron/operator-system.crontab` is a local cron draft.
- `github-actions/operator-automations.yml` is a workflow draft.
- `publishers.md` lists configured outbox publishers.
- `runtime-export.json` records the enabled automation IDs and written files.

Create one dry-run packet and one outbox item:

```bash
python3 hub/scripts/run_automation.py --root . --automation-id morning-control-panel
python3 hub/scripts/publish_status.py --root . --publisher status --message "Ready for review"
python3 hub/scripts/deliver_outbox.py --root . --publisher status --latest
```

`deliver_outbox.py` writes a delivery receipt by default. It sends externally
only when `--execute` is passed and the selected delivery adapter is configured.
Supported adapters are `slack-webhook`, `webhook-json`, `github-issue`,
`command`, and no-op outbox-only delivery.

## 5. Configure Backup Transfer

Start with a dry-run report:

```bash
python3 hub/scripts/backup_verify.py --root . --write-report
python3 hub/scripts/backup_transfer.py --root . --write-report
```

Execute only after reviewing `backup.transfer.destination`, `backup.exclude`,
and the generated report:

```bash
python3 hub/scripts/backup_transfer.py --root . --execute --write-report
```

The starter supports `local-copy` and `rsync` methods. Keep private credentials
and mounted/cloud-specific secrets outside the tracked workspace.

## 6. Configure Chat File Fetch

Use `chat_file_fetch.py` when a chat attachment is hosted remotely and needs to
be captured before intake:

```bash
python3 hub/scripts/chat_file_fetch.py --root . --provider direct-url --url file:///path/to/upload.txt
python3 hub/scripts/chat_file_intake.py --root . --work-item work-items/<id> --source-file local-private/chat-downloads/<file>
```

Configured provider types:

- `direct-url` downloads from a URL or `url_env`.
- `slack-web-api` resolves `--file-id` through Slack Web API with a token from
  `OPERATOR_SLACK_FILE_TOKEN` or the configured `token_env`.
- `command` runs an organization-owned command with `OPERATOR_FILE_ID`,
  `OPERATOR_FILE_URL`, `OPERATOR_OUTPUT_PATH`, and `OPERATOR_ROOT`.

Fetched files and sidecar metadata stay under ignored `local-private/` until
they are intentionally routed into a work item with `chat_file_intake.py`.

## 7. Initialize Version Control

Initialize or connect the workspace to its owning repository, then commit the
tracked scaffold. Keep `local-private/`, credentials, and exported private
packets ignored.

Before each substantive run, refresh current state, perform the work, update
memory, commit coherent changes, and verify no hidden local-only parking remains.
