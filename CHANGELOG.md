# Changelog

## 0.4.0 - 2026-07-02

- New `ops.py` single entry point (`startup`, `doctor`, `run`, `close`,
  `search`, `review`, `compact`, `sweep`, `wiki`).
- New `retention_sweep.py` retires old runtime artifacts (automation runs,
  delivery receipts, sync reports, morning briefs, digests, backups) into
  `archive/retired/` — dry-run first, config-driven window.
- New `config_check.py` validates org.json (types, cron fields, delivery and
  provider types, budgets) before other scripts trip on mistakes.
- Cross-process locks around LESSONS.md writes, action-log rotation, and
  retention sweeps.
- `package_gate.py --draft-task` auto-drafts the follow-up task when a
  package is BLOCKED.
- `upgrade_workspace.py --check` exits nonzero when kit updates are
  available and writes a marker the state digest surfaces.
- Overdue scheduled automations now appear as advisory memory-health notes.
- `scripts/demo_walkthrough.py` drives the full loop end to end in a
  throwaway workspace; tag-push `release.yml` publishes the versioned
  tarball and checksum manifest as a GitHub Release.

## 0.3.0 - 2026-07-02

- Standard Ratchet embedded in all automation prompts and installed bundles,
  not only `run_automation.py` packets.
- `sync_workspace.py` is now dry-run-first; `--execute` applies pulls and
  stash-syncs.
- `preflight_capabilities.py` checks adapter prerequisites (rsync, gh,
  delivery/token env vars) and no longer misreports connectors as degraded.
- Timeouts on all external subprocess calls (delivery command, gh issue,
  rsync, chat-file command fetch, agent invocation).
- `deliver_outbox.py` and `backup_transfer.py` accept `--run-id` and record it.
- `memory_health.py` budgets recent no-improvement closes and surfaces repo
  sync risks; `run_close.py --lesson` adds/re-confirms lessons inline.
- New `lesson_add.py` (add / re-confirm with hit counts / prune) and
  `wiki_compile.py` (compiles `hub/wiki/overview.md`).
- `run_automation.py --invoke` executes packets with a configured
  `runtime.agent_command` and records `invoke.json`.
- Kit version stamped into scaffolds and upgrades; `feeds` config block for
  the external feed digest; docs reconciled with the real memory tree.

## 0.2.0 - 2026-07-02

- Memory budgets (`memory_health.py`), action-log rotation
  (`memory_compact.py`), `LESSONS.md` improvement ratchet, run closeout
  records, health trend, automation heartbeat, ranked memory search,
  `upgrade_workspace.py` with template manifest, GitHub Actions CI.

## 0.1.0 - 2026-07-01

- Initial public operator system starter kit.
