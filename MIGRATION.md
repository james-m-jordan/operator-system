# Migration Guide

Use this checklist when adapting an existing team, project, or operator
workspace into the generalized operator system.

## 1. Inventory Current Surfaces

Map existing folders to the portable surfaces:

| Existing Surface | Operator-System Target |
| --- | --- |
| admin policy, runbooks, scripts | `hub/` |
| durable memory, logs, decisions | `hub/MEMORY/` |
| active projects, clients, cases, initiatives | `work-items/` |
| shared protocols, examples, standards | `knowledge-base/` |
| private exports, receipts, credentials-derived evidence | `local-private/` |

Do not copy secrets or private attachments into tracked files.

## 2. Normalize Memory

Create compact current-state files first:

- `hub/MEMORY/state-digest.md`
- `hub/MEMORY/capabilities.json`
- `hub/MEMORY/LANDMARKS.md`

Move long narratives into `hub/MEMORY/agent-action-log.md` or dated reports.
Use `LANDMARKS.md` only for short pointers that should affect current behavior.

## 3. Convert Work Packages

Each active work item should have:

- a canonical folder under `work-items/`
- source files or authoritative inputs
- metadata explaining each source-bearing file, row, sheet, attachment, or
  message
- a README with owner, requested outcome, constraints, and decision boundary

Run:

```bash
python3 hub/scripts/package_gate.py --root . --work-item work-items/<id>
```

If the package is incomplete, write a collaborator task draft instead of running
partial analysis.

## 4. Port Automations

Start from `hub/automations/automation-manifest.json` and edit the prompt files
under `hub/automations/prompts/`.

For every automation, confirm:

- connector needs are explicit
- expected writes are scoped
- closeout says where memory and status go
- no organization-specific names or hard-coded paths remain

Then export the runtime drafts:

```bash
python3 hub/scripts/install_automations.py --root . --out .operator-automations
python3 hub/scripts/export_runtime_adapters.py --root .
```

## 5. Configure Delivery And Backup

Keep publication and backups in dry-run mode until the operator has reviewed the
target config.

For publishers:

```bash
python3 hub/scripts/publish_status.py --root . --publisher status --message "Dry-run status"
python3 hub/scripts/deliver_outbox.py --root . --publisher status --latest
```

Set environment variables such as `OPERATOR_STATUS_WEBHOOK_URL` or
`OPERATOR_TASK_REPO` only in the runtime environment. Do not commit secrets.

For backups:

```bash
python3 hub/scripts/backup_verify.py --root . --write-report
python3 hub/scripts/backup_transfer.py --root . --write-report
```

Use `--execute` only after the dry-run report names the intended destination and
exclusions.

For chat-hosted files:

```bash
python3 hub/scripts/chat_file_fetch.py --root . --provider direct-url --url file:///path/to/upload.txt
python3 hub/scripts/chat_file_intake.py --root . --work-item work-items/<id> --source-file local-private/chat-downloads/<file>
```

Use `file_sources.chat.providers` to map each existing chat platform to
`direct-url`, `slack-web-api`, or an organization-owned `command` adapter.

## 6. Cut Over In Stages

1. Run preflight, sync, index, and digest locally.
2. Run one automation with `run_automation.py --print-prompt` and review the
   prompt packet.
3. Create outbox status items instead of sending directly.
4. Dry-run `deliver_outbox.py` and `backup_transfer.py` before using
   `--execute`.
5. Fetch one remote chat attachment into `local-private/` and then route it with
   `chat_file_intake.py`.
6. Install a scheduler only after the generated cron or workflow file has been
   reviewed by the operator.
7. Enable live connector publishers after dry-run outbox behavior is clean.
