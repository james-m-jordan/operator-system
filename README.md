# Operator System Starter Kit

This folder is the first distributable, organization-neutral form of the
`lia-live` operating system. It keeps the useful architecture from the current
workspace while removing Jordan Lab and biology-specific assumptions.

The target user is an operator, principal, founder, program lead, or small team
that wants an agent-operated workspace with:

- a hub for admin policy, memory, automation specs, and cross-work synthesis
- work repositories or folders that hold canonical task packages
- structured memory that survives across agent sessions
- recurring automations for inbox triage, chat intake, planning, system review,
  operations checklists, backups, feed digests, and receipt packets
- explicit permission boundaries between admin control surfaces and team work
- clean repo hygiene, run logs, and distributable prompts

## Current Status

This is a packaged starter kit, not a hosted application. It contains:

- `BLUEPRINT.md` - the generalized system architecture and current porting map
- `COMPLETION-MATRIX.md` - the generated release audit matrix
- `LICENSE` - Apache License 2.0 terms for reuse and redistribution
- `config/org.example.json` - an example organization config
- `templates/` - organization-neutral starter files
- `scripts/scaffold_workspace.py` - a standard-library scaffold command
- generated helper scripts for preflight, sync reporting, memory indexing,
  state digest refresh, work-package gating, automation installation, task
  drafting, backup verification, backup transfer, chat-file fetch/intake,
  runtime adapter export, run packet creation, outbox status publication, and
  optional outbox delivery
- `INSTALL.md`, `MIGRATION.md`, and `RELEASE-CHECKLIST.md` - operator setup,
  migration, and packaging checklists
- `scripts/package_release.py` - builds a versioned tarball plus checksum
  manifest for handoff
- `tests/` - smoke tests for the scaffold command

## How It Works

```
╔══════════════════════════ STARTER KIT (this repo) ══════════════════════════════════╗
║   templates/  +  config/org.json          CI: compile · tests · release audit       ║
║                                                                                      ║
║   scaffold_workspace.py ──render──▶ NEW WORKSPACE     (file hashes ▶ template-      ║
║   upgrade_workspace.py ──safe updates──▶ EXISTING      manifest.json + kit version) ║
║        · adds new files, updates unmodified ones                                     ║
║        · skips locally-edited files as conflicts                                     ║
║        · never touches hub/MEMORY/ or hub/admin-docs/                                ║
╚══════════════════════════════════════════╤═══════════════════════════════════════════╝
                                           ▼
┌────────────────────────────── GENERATED WORKSPACE ───────────────────────────────┐
│  AGENTS.md ····· agent rules + startup checklist + improvement ratchet           │
│  work-items/ ··· canonical task packages (gated: source + metadata + context)    │
│  knowledge-base/ shared procedures      local-private/ ·· ignored, never in git  │
│                                                                                   │
│  hub/ ─ admin control room                                                        │
│  ├─ MEMORY ─ compact, budget-enforced (read every run)                            │
│  │    state-digest.md   ◀─ regenerated: counts, health, trend, heartbeat         │
│  │    LANDMARKS.md      ◀─ durable operating contracts                           │
│  │    LESSONS.md        ◀─ reusable rules with hit counts   ◀── THE RATCHET      │
│  │    capabilities.json ◀─ preflight: tools, rsync/gh, token env vars            │
│  │    indexes/          ◀─ work items, blockers, memory-health-history.jsonl     │
│  ├─ MEMORY ─ deep history (searchable via memory_search.py)                       │
│  │    agent-action-log.md ──over budget──▶ archive/action-log-<year>.md          │
│  │    automation-runs/<id>/ (run.md · run.json · close.json · invoke.json)       │
│  │    self-optimization/ · repo-syncs/ · outbox/ · morning/ · backups/           │
│  ├─ wiki/overview.md    ◀─ compiled synthesis (wiki_compile.py)                  │
│  └─ automations/        ◀─ manifest + 9 prompts (all carry the Standard Ratchet) │
└───────────────────────────────────────────────────────────────────────────────────┘

              THE RUN LOOP ── "every turn gets a little better"
              ─────────────────────────────────────────────────
   cron / GitHub Actions / operator
        │
        ▼
   run_automation.py --invoke
        │  builds packet:  prompt + Active Lessons (injected) + Required Closeout
        ▼
   runtime.agent_command ["claude","-p","{packet}"]     (timeout, invoke.json)
        │
        ▼  agent does bounded work, then MUST close out:
   ┌─────────────────────────────────────────────────────────────────┐
   │ 1. log the run          ▶ agent-action-log.md                   │
   │ 2. leave ONE improvement▶ lesson_add.py (fuzzy dedupe, hits++)  │
   │                           or correct / prune a memory entry     │
   │ 3. refresh health       ▶ memory_health.py --write (trend line) │
   │ 4. close the run        ▶ run_close.py (outcome + improvement)  │
   └─────────────────────────────────────────────────────────────────┘

              THE FLYWHEEL ── lessons become permanent behavior
              ─────────────────────────────────────────────────
        every run reads LESSONS.md ◀────────────────────────────┐
                    │                                            │
        confirms/adds lessons (hits++)                           │
                    │                                            │
                    ▼            hits ≥ 3                        │
        system-review-loop ──promotes──▶ LANDMARKS contracts     │
        (weekly)    │                     or prompt/script fixes─┘
                    ├─ prunes stale lessons & Top-Of-Mind entries
                    ├─ memory_compact.py rotates the action log
                    ├─ wiki_compile.py refreshes the synthesis
                    └─ exit gate: memory_health.py --strict must pass

              WATCHDOGS ── silence never looks like success
              ─────────────────────────────────────────────
   · budgets: LANDMARKS/digest/LESSONS lines, log entries, unclosed runs,
              recent no-improvement closes  (memory_health.py, --strict gates)
   · heartbeat: state digest flags OVERDUE / never-run scheduled automations
   · trend: memory-health-history.jsonl deltas shown in every digest
   · preflight: adapter prerequisites checked before they can fail mid-run
   · dry-run-first everywhere: sync, compact, transfer, deliver need --execute
```

In one paragraph: the **kit** stamps out and upgrades **workspaces**; each
workspace runs **automations** whose packets carry the current lessons in and
require one improvement out (the ratchet); the **review loop** periodically
compresses repeated lessons into permanent contracts and prunes the rest; and
the **watchdogs** make decay visible — budgets for memory bloat, a heartbeat
for dead automations, and a health trend that shows whether "a little better
every turn" is actually happening.

## Portable Institutional Memory

Agent frameworks ship code. This system ships **judgment** — versioned,
auditable, and portable across an organization:

- **Lesson Packs** (`hub/scripts/lesson_pack.py`). Lessons here are
  structured data: dated, hit-counted, organization-neutral rules. Export the
  battle-tested ones (`ops pack export --min-hits 3`) and import them into
  any other workspace, where they merge through the same fuzzy dedupe the
  ratchet uses. A rule learned by one team propagates to every workspace on
  the next cycle — the org learns once, everywhere. Packs carry rules, not
  data: evidence paths are stripped by default and the source stays anonymous
  unless you opt in, so consultancies and multi-team companies can share
  operational judgment without sharing client information.
- **The Operator Report** (`hub/scripts/operator_report.py`, or
  `ops report`). A periodic executive brief compiled from records the system
  already keeps: runs per automation with outcomes, improvements recorded,
  active lessons and re-confirmations, the memory-health trend, executed
  deliveries, and any overdue automations. The compounding loop becomes
  visible to the person who signs the check.
- **Receipts** (`ops verify`). Every run closeout is appended to a
  hash-chained ledger (`hub/MEMORY/indexes/close-chain.jsonl`), so the run
  history is tamper-evident on top of git's own history. Every agent action
  has a receipt, every receipt is chained, and the whole thing lives in your
  repo — not someone else's cloud.

## Quick Start

See the whole loop working in under a minute:

```bash
python3 scripts/demo_walkthrough.py
```

Preview the generated workspace in a throwaway path:

```bash
python3 scripts/scaffold_workspace.py \
  --config config/org.example.json \
  --out /tmp/operator-system-demo \
  --force
```

Run the smoke tests:

```bash
python3 -m unittest tests/test_scaffold_workspace.py
python3 scripts/audit_release.py --json
python3 scripts/package_release.py --out /tmp/operator-system-release
```

After scaffolding, the generated workspace can refresh its own startup state
with one command:

```bash
cd /tmp/operator-system-demo
python3 hub/scripts/ops.py startup
```

or with the individual helpers:

```bash
cd /tmp/operator-system-demo
python3 hub/scripts/config_check.py --root .
python3 hub/scripts/preflight_capabilities.py --root .
python3 hub/scripts/sync_workspace.py --root .
python3 hub/scripts/memory_index_refresh.py --root . --write --validate
python3 hub/scripts/state_digest.py --root .
python3 hub/scripts/memory_health.py --root . --write
python3 hub/scripts/install_automations.py --root . --out .operator-automations
python3 hub/scripts/export_runtime_adapters.py --root .
python3 hub/scripts/run_automation.py --root . --automation-id morning-control-panel
python3 hub/scripts/run_close.py --root . --latest --outcome success --improvement lesson --improvement-ref hub/MEMORY/LESSONS.md
python3 hub/scripts/memory_search.py --root . --query "scaffold"
python3 hub/scripts/wiki_compile.py --root .
python3 hub/scripts/publish_status.py --root . --publisher status --message "Ready for review"
python3 hub/scripts/deliver_outbox.py --root . --publisher status --latest
python3 hub/scripts/backup_transfer.py --root . --write-report
printf 'example upload\n' > /tmp/operator-upload.txt
python3 hub/scripts/chat_file_fetch.py --root . --provider direct-url --url file:///tmp/operator-upload.txt
```

See `INSTALL.md` for the full bootstrap flow and `MIGRATION.md` for bringing an
existing workspace into this structure.

When the starter kit gains new templates or script fixes, existing scaffolded
workspaces can adopt them without losing local data:

```bash
python3 scripts/upgrade_workspace.py --workspace /path/to/workspace
python3 scripts/upgrade_workspace.py --workspace /path/to/workspace --execute
```

The upgrade never touches `hub/MEMORY/` or `hub/admin-docs/`, and skips any
file the workspace has modified locally (reported as conflicts).

## Distribution Boundaries

This package should remain independent of the live Jordan Lab data model:

- Use `work-items/` instead of `team-projects/`.
- Use people/work-item bios instead of trainee/project bios.
- Use general package gates instead of biology assay gates.
- Keep connector names configurable.
- Keep private/local artifacts ignored by default.
- Treat all generated files as starting points that downstream organizations
  can edit for their own policies.

## Optional Follow-Up Adapters

The release audit passes for the portable starter kit. Future adapters can
extend the generic command/webhook/local-copy interfaces when an organization
needs deeper native integrations:

- provider-native scheduler/publisher plugins beyond cron, GitHub Actions,
  webhook, command, and GitHub-issue adapters
- richer issue/task publisher integrations for Linear, Jira, or email
- cloud-storage-specific backup adapters beyond local-copy and rsync
- polished provider-specific chat file recipes beyond direct URL, Slack Web API,
  and command adapters

Those adapters should read an org config rather than hard-coded paths, repo
names, Slack channels, or lab-specific metadata fields.

## License

Licensed under the Apache License, Version 2.0. See `LICENSE`.

Copyright 2026 James M. Jordan.
