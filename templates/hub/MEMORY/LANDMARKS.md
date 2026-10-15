# LANDMARKS

Purpose: compact startup pointer map for `{{ORG_NAME}}`. Read relevant entries when the task needs them. Keep it small.

Update rule: include only current decision points, durable operating contracts,
and routes to deeper context. Put full narratives in `agent-action-log.md` or
dated reports.

## Top Of Mind

- Initial scaffold created on {{DATE}}. Details: `hub/MEMORY/agent-action-log.md`.

## Durable Operating Contracts

| Contract | Detail Source |
| --- | --- |
| Read `hub/MEMORY/state-digest.md` as the compact current-state working set. | `hub/MEMORY/state-digest.md` |
| Check `hub/MEMORY/capabilities.json` before connector-dependent work. | `hub/MEMORY/capabilities.json` |
| Look up relevant, evidence-backed lessons on demand. | `hub/MEMORY/LESSONS.md` |
| Admin policy and memory live in `hub/`; execution work belongs in `work-items/`. | `AGENTS.md`; `hub/admin-docs/permissions.md` |
| Substantive runs update the action log and relevant bios/comms memory. | `AGENTS.md`; `hub/MEMORY/agent-action-log.md` |
| No-change runs are healthy; change memory only when new evidence warrants it. | `AGENTS.md`; `hub/MEMORY/LESSONS.md` |
| Compact memory stays within `memory_budgets`; check with `memory_health.py`. | `hub/config/org.json`; `hub/MEMORY/indexes/memory-health.json` |
| Private packets and credentials-derived exports stay out of git. | `AGENTS.md`; `.gitignore` |

## Detail Lookup Map

| Need | Start Here |
| --- | --- |
| Current state | `hub/MEMORY/state-digest.md` |
| Tool health | `hub/MEMORY/capabilities.json` |
| Reusable lessons | `hub/MEMORY/LESSONS.md` |
| Memory budget health | `hub/MEMORY/indexes/memory-health.json` |
| Run history | `hub/MEMORY/agent-action-log.md` |
| People context | `hub/MEMORY/people-bios.md` |
| Work-stream context | `hub/MEMORY/work-item-bios.md` |
| Communication decisions | `hub/MEMORY/comms.md` |
