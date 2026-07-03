# Generalized Operator System Blueprint

## Objective

Create a distributable version of the `lia-live` system: a portable operating
workspace with automations, memory, repo hygiene, and action routing that can
serve many organization types.

## Architecture

The generalized workspace has four top-level surfaces:

| Surface | Purpose |
| --- | --- |
| `hub/` | Admin control room: policy, automation specs, memory, scripts, configs, and compiled synthesis. |
| `work-items/` | Canonical execution folders or nested repos for projects, clients, programs, cases, initiatives, or experiments. |
| `knowledge-base/` | Shared procedures, standards, examples, reusable references, and training moments. |
| `local-private/` | Ignored local-only packets for private attachments, receipts, exports, and credentials-derived evidence. |

The system is prompt-first and file-first. Agents should be able to start from
the current checked-out files, run a small preflight, act on bounded work, log
what changed, and leave repo state clean.

## Memory Model

Memory is layered so startup reads are small and deeper history remains
queryable:

| File Or Folder | Role |
| --- | --- |
| `hub/MEMORY/state-digest.md` | Regenerated current-state working set. Read on every admin run. |
| `hub/MEMORY/capabilities.json` | Tool and connector health flags. Read before assuming a capability works. |
| `hub/MEMORY/LANDMARKS.md` | Compact top-of-mind pointer map. No long run narratives. |
| `hub/MEMORY/LESSONS.md` | Compact reusable behavior rules with hit counts. Read on every admin run; the per-run improvement ratchet. |
| `hub/MEMORY/indexes/memory-health.json` | Budget compliance snapshot for compact memory surfaces, plus an append-only history trend. |
| `hub/MEMORY/agent-action-log.md` | Chronological account of substantive work. Rotated into `archive/` when over budget. |
| `hub/MEMORY/people-bios.md` | Durable person context: responsibilities, preferences, constraints, active work. |
| `hub/MEMORY/work-item-bios.md` | Durable work-stream context: scope, status, blockers, next actions. |
| `hub/MEMORY/comms.md` | Important communication context and decisions. |
| `hub/MEMORY/references.md` | Distilled reusable external-reference takeaways. |
| `hub/MEMORY/repo-syncs/` | Dated sync/preflight reports. |
| `hub/MEMORY/archive/` | Retired reports and inactive automation artifacts. |
| `hub/wiki/` | Slower-changing synthesized views compiled from memory and work-item state. |

## Generalized Automations

The live `lia-live` automation set maps to these portable modules:

| Live Pattern | General Module | Distribution Status |
| --- | --- | --- |
| Personal Agent Morning Plan | Morning Control Panel | Spec template included. |
| Jordan Lab Slack Codex Daily Turn | Chat Intake And Action Turn | Spec template included. |
| Slack Science Lit. Scrape To RSS | External Feed Digest | Spec template included. |
| Conference Planning Refresh | Opportunity Planning Refresh | Spec template included. |
| Lia-live Agent Dreaming Loop | System Review Loop | Spec template included. |
| Lab Maintenance Checklist Scan | Operations Checklist Scan | Spec template included. |
| Weekly Lia-Live Backup To Memory1 | Workspace Backup | Spec template included. |
| Toria PCard Receipt Packet | Receipt Packet Assembly | Spec template included. |
| Slack File Intake Skill | Chat File Intake | Needs configurable helper port. |
| `preflight_capabilities.py` | Capability Snapshot | Generic helper included. |
| `sync_clean_repos.py` | Workspace Sync Report | Generic helper included. |
| `memory_index_refresh.py` | Work-Item Memory Index | Generic helper included. |
| `state_digest.py` | Current-State Digest | Generic helper included. |
| Memory budget enforcement | Memory Health Snapshot (`memory_health.py`) | Generic helper included. |
| Action log rotation | Memory Compaction (`memory_compact.py`) | Generic helper included. |
| `work_package_gate.py` | Work Package Gate | Generic helper included. |
| Automation TOML/prompt installs | Automation Manifest Installer | Generic helper included. |
| Easy-mode issue drafting | Task Draft Helper | Generic helper included. |
| Weekly backup verification | Backup Verification | Generic helper included. |
| Slack file intake routing | Chat File Fetch + Intake | Direct URL, Slack Web API, command fetch, local byte preservation, and canonical intake helpers included. |
| Cron/GitHub scheduled runs | Runtime Adapter Export | Scheduler drafts and run-packet creation included; live connector publishing still external. |
| Slack/status posting | Publisher Outbox + Delivery | Markdown/JSON outbox helper plus dry-run-first webhook, command, and GitHub issue delivery included. |
| Rsync/local backup transfer | Backup Transfer | Dry-run-first local-copy and rsync transfer helper included. |

## Work Package Gate

The generalized package gate should require:

1. Source files or authoritative inputs exist in the canonical work-item path.
2. Metadata maps every source-bearing file, row, sheet, attachment, or message to
   its meaning.
3. Work context explains the question, requested outcome, owner, constraints,
   and decision boundary.
4. The analysis or transformation method is recorded.
5. The result separates verified facts, assumptions, and human decisions.

If any requirement is missing, the agent creates a follow-up task instead of
running partial analysis.

## Porting Rules

- Replace lab-specific names with config values.
- Replace `team-projects/proj###` with configurable work-item roots.
- Keep admin-only surfaces separate from team-facing work surfaces.
- Use connector capability flags before attempting connector actions.
- Keep local-private evidence ignored and out of commits.
- Preserve original source files and attachments.
- Record substantive runs in the action log and refresh compact memory surfaces
  only when they change current behavior.

## Release Criteria

The distributable version is complete when:

1. A clean workspace can be scaffolded from config.
2. The scaffolded workspace can run preflight, sync, memory-index, state-digest,
   and package-gate commands.
3. Every generalized automation has an installable prompt/spec and expected
   memory closeout.
4. Core scripts read config instead of hard-coded Jordan Lab paths.
5. A versioned release archive and checksum manifest can be built from the
   distribution folder.
6. A release audit can regenerate `COMPLETION-MATRIX.md` with all required
   files, automation specs, config surfaces, generated workspace neutrality, and
   archive contents passing.
7. Tests cover scaffold generation, config validation, memory index generation,
   repo sync reporting, automation installation, task drafting, backup
   verification, backup transfer, chat-file fetch/intake, runtime adapter
   export, run packets, publisher outbox creation, and delivery receipts.
8. Documentation explains how to install, customize, run automations, and migrate
   an existing organization into the system.
