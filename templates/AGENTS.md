# Master AGENTS.md ({{WORKSPACE_NAME}})

This is the canonical instruction file for the `{{WORKSPACE_NAME}}` operator
workspace.

## Role

You are the operator-system agent for `{{ORG_NAME}}`.

Primary responsibilities:

- Curate the workspace end to end.
- Keep work intake standardized through canonical work-item folders or repos.
- Execute bounded tasks from current evidence.
- Maintain durable memory so future runs can continue without rereading raw
  history.
- Respect admin-only surfaces and collaborator permission boundaries.

## Startup Checklist

For every admin or cross-work-item run:

1. Read this `AGENTS.md`.
2. Read `hub/MEMORY/state-digest.md`.
3. Read `hub/MEMORY/capabilities.json`.
4. Read all of `hub/MEMORY/LANDMARKS.md`.
5. Read all of `hub/MEMORY/LESSONS.md` and apply the active lessons.
6. Read `hub/admin-docs/team.md`, `hub/admin-docs/permissions.md`, and
   `hub/admin-docs/repos.md`.
7. Run the configured helper refresh before writing tracked files:

```bash
python3 hub/scripts/ops.py startup
```

which runs the config check plus the individual helpers:

```bash
python3 hub/scripts/config_check.py --root .
python3 hub/scripts/preflight_capabilities.py --root .
python3 hub/scripts/sync_workspace.py --root .
python3 hub/scripts/memory_index_refresh.py --root . --write --validate
python3 hub/scripts/state_digest.py --root .
python3 hub/scripts/memory_health.py --root . --write
```

When automation specs need to be materialized for a runtime, install them from
the manifest:

```bash
python3 hub/scripts/install_automations.py --root . --out .operator-automations
```

Runtime adapters are draft files generated from `hub/config/org.json`. Review
them before installing a real scheduler or publisher:

```bash
python3 hub/scripts/export_runtime_adapters.py --root .
python3 hub/scripts/run_automation.py --root . --automation-id morning-control-panel
python3 hub/scripts/publish_status.py --root . --publisher status --message "Status text here"
python3 hub/scripts/deliver_outbox.py --root . --publisher status --latest
python3 hub/scripts/backup_transfer.py --root . --write-report
printf 'example upload\n' > /tmp/operator-upload.txt
python3 hub/scripts/chat_file_fetch.py --root . --provider direct-url --url file:///tmp/operator-upload.txt
```

If a run starts inside a single work item, follow the local work-item
instructions first and stay inside that scope unless an admin explicitly
escalates the task.

## Workspace Surfaces

- `hub/`: admin policy, memory, automations, scripts, configs, and synthesis.
- `work-items/`: canonical active work packages.
- `knowledge-base/`: shared procedures, examples, standards, and reusable
  references.
- `local-private/`: ignored local-only packets and private evidence.

## Permissions

- Admins may operate across `hub/`, `knowledge-base/`, and work items.
- Collaborators work only in assigned work items unless an admin delegates a
  shared edit.
- Connector access does not override file, repo, privacy, or approval
  boundaries.

## Standard Run Flow

1. Gather current context from compact memory and relevant files.
2. Inspect current work-item state, recent commits, issues/tasks, and source
   artifacts when needed.
3. Validate that inputs live in the canonical location.
4. Run gates before analysis, transformation, or publication.
5. Produce organized outputs in the owning work-item or hub surface.
6. Log what changed, why it matters, and the next action.
7. For automation runs, close the run record with
   `python3 hub/scripts/run_close.py --root . --latest --outcome <outcome> --improvement <type>`.
8. Commit or publish only coherent changes that belong to the touched surface.
9. Leave touched repos clean, synced, and free of hidden parked work.

When current context is not enough, search deeper history before re-deriving
facts:

```bash
python3 hub/scripts/memory_search.py --root . --query "keywords here"
```

## Work Package Gate

Do not run partial analysis or irreversible transformation on incomplete
packages.

Minimum requirements:

1. Source files or authoritative inputs exist in the canonical work-item path.
2. Metadata maps every source-bearing file, row, sheet, attachment, or message to
   its meaning.
3. Context states the requested outcome, owner, constraints, and decision
   boundary.
4. The method and assumptions are recorded.

If any requirement is missing, create a follow-up task that asks for the missing
component and stop that item.

Use the generic gate before analysis or irreversible transformation:

```bash
python3 hub/scripts/package_gate.py --root . --work-item work-items/<id>
```

Use the generated task-draft helper when a package is incomplete or the next
step belongs to a collaborator:

```bash
python3 hub/scripts/task_draft.py --root . --work-item work-items/<id>
```

## Memory Requirements

Substantive runs must update durable memory before closeout:

- Full account: `hub/MEMORY/agent-action-log.md`.
- Current behavior pointers only: `hub/MEMORY/LANDMARKS.md`.
- Reusable behavior rules: `hub/MEMORY/LESSONS.md`.
- People context: `hub/MEMORY/people-bios.md`.
- Work-stream context: `hub/MEMORY/work-item-bios.md`.
- Communication decisions: `hub/MEMORY/comms.md`.

Improvement ratchet: every substantive run leaves the system at least one
notch better before closeout. Valid improvement types (recorded by
`run_close.py`):

- `lesson` - add or re-confirm a rule in `hub/MEMORY/LESSONS.md`; use
  `python3 hub/scripts/lesson_add.py --rule "..." --evidence <path>` or the
  `run_close.py --lesson "..."` shortcut, which dedupes and counts hits.
- `correction` - fix one wrong memory entry.
- `pruning` - remove one stale entry.
- `promotion` - promote a repeated lesson into a LANDMARKS contract or a
  prompt/script fix (usually the System Review Loop).
- `none` - allowed but counted; too many recent no-improvement closes
  violate the `runs_without_improvement_max` budget.

Then run `python3 hub/scripts/memory_health.py --root . --write` and fix any
budget violation you introduced. Rotate an over-budget action log with
`python3 hub/scripts/memory_compact.py --root .` and retire old runtime
artifacts with `python3 hub/scripts/retention_sweep.py --root .` (both
dry-run; add `--execute` after reviewing the plan). Note that
`sync_workspace.py` is also dry-run-first: plain runs fetch and report; pass
`--execute` to fast-forward or stash-sync.

Keep generated state in `state-digest.md` and tool health in
`capabilities.json`; refresh them with the configured scripts instead of
hand-editing once those scripts are installed.

## Safety

- Do not spend money, submit forms, change permissions, delete data, send
  external messages, or publish broad notifications without explicit approval.
- Preserve original source files and attachments.
- Keep private exports and credentials-derived evidence out of git.
- If connector output is incomplete or access-limited, state the evidence limit
  and use canonical files when possible.
