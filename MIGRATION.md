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
- `hub/MEMORY/LESSONS.md`

Move long narratives into `hub/MEMORY/agent-action-log.md` or dated reports.
Use `LANDMARKS.md` only for short pointers that should affect current behavior.
Use `LESSONS.md` for short reusable behavior rules with hit counts. Check the
compact files against budgets with
`python3 hub/scripts/memory_health.py --root . --write` and rotate an
over-budget action log with `python3 hub/scripts/memory_compact.py --root .`
(dry-run; add `--execute` after reviewing the plan).

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

## Upgrading to 0.6.0

First inspect the dry-run plan from `scripts/upgrade_workspace.py --workspace
<path>`. Apply unchanged templates with `--execute`; resolve reported conflicts
without replacing local decisions or evidence. Do not point this at an unscaffolded
production workspace and assume its policy has migrated.

- The new policy takes precedence over older template instructions requiring all
  context on every run, one improvement per run, promotion at three hits, or
  pruning unused lessons. User-authored decisions retain their authority.
- `hub/MEMORY/` and `hub/admin-docs/` remain user-owned and are never overwritten.
  Review retained LANDMARKS/LESSONS for those obsolete template rules. Historical
  entries and counts are evidence of prior bookkeeping, not verified learning.
- `runs_without_improvement_max` is deprecated and ignored; remove it when editing
  config. `improvement=none` is healthy, and complete quiet scans use `no_op`.
- Use `ops observe` for read-only configuration checks and `ops prepare --repo ...`
  for selected dependencies. Full startup is for broad maintenance. Automatic
  stashing has been removed, including explicit sync execution.
- Success/no-op closeout now requires `--evidence` and passing `--check name=pass`
  values matching packet requirements. Update custom wrappers and prompts before
  unattended execution. Use explicit run IDs; ambiguous `--latest` is rejected.
- `--invoke` delivers packet text on stdin and sets the working directory. The
  old `{packet}` path substitution remains supported. Exit zero without a valid
  chained closeout is incomplete (runner code 3), including the example echo stub.
- Existing chain records remain readable. New receipts bind all closeout fields;
  repeated closes are idempotent and corrections require explicit amendments.
- Delivery retry state is stored separately from retained receipts. Historical
  executed receipts prevent silent resend. Uncertain sends need destination
  reconciliation, not automatic expiration. Preserve `outbox-delivery-state/`.
- The default package gate now checks actual file coverage. Unsupported maps or
  missing meanings need conversion/review; structure-only success never establishes
  readiness for analysis. Index status is `ready_for_review` after the generic gate.
- Schedule health now uses actual timezone-aware occurrences and successful
  completion. Historical success records without checks/evidence do not establish
  current verified health. Explicit `max_gap_hours` overrides remain supported.

Regenerate installed automation bundles and scheduler drafts after upgrading;
review them before deployment. Test a quiet scan, a complete fixture, an incomplete
package, an interrupted run, and a duplicate delivery against a local test sink.
