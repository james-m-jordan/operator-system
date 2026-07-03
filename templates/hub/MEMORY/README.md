# Memory Layer

This folder stores durable operational memory for `{{ORG_NAME}}`.

Use compact files for startup and deeper logs for search:

- `state-digest.md` - current-state working set.
- `capabilities.json` - connector and tool health flags.
- `LANDMARKS.md` - compact current-behavior pointers.
- `LESSONS.md` - compact reusable behavior rules with hit counts; the
  per-run improvement ratchet. Manage with `hub/scripts/lesson_add.py`.
- `agent-action-log.md` - chronological account of substantive work.
  Rotated into `archive/` by `hub/scripts/memory_compact.py`.
- `people-bios.md` - durable person context.
- `work-item-bios.md` - durable work-stream context.
- `comms.md` - important communication context and decisions.
- `references.md` - reusable external-reference takeaways.

Generated and runtime folders:

- `indexes/` - work-item, blocker, and memory-health indexes, plus the
  `memory-health-history.jsonl` trend (created by the refresh scripts;
  `memory-health.json` appears after the first `memory_health.py --write`).
- `automation-runs/` - run packets, `close.json` outcome records, and
  `invoke.json` agent-invocation results.
- `self-optimization/` - dated system-review-loop reports.
- `morning/` - dated morning-control-panel briefs.
- `outbox/` and `outbox-deliveries/` - publisher payloads and delivery
  receipts.
- `task-drafts/` - collaborator task drafts from `task_draft.py`.
- `feed-digests/` - external feed digest artifacts.
- `backups/` - backup verification and transfer reports.
- `opportunities.md` - opportunity planning memo (when that automation runs).
- `repo-syncs/` - dated sync reports.
- `archive/` - rotated action-log years, retired report systems, and
  inactive automation artifacts.

Slower-changing synthesis lives in `hub/wiki/`, compiled by
`hub/scripts/wiki_compile.py`.

Keep raw history, private exports, and credentials-derived evidence outside
this folder unless the file is explicitly safe to commit.
