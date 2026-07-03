# LESSONS

Purpose: compact self-improvement rules for `{{ORG_NAME}}`. Read this whole
file on admin runs, right after `LANDMARKS.md`. Keep it within the
`lessons_max_lines` budget in `hub/config/org.json`.

Update rules:

- Every substantive run leaves the system at least one notch better: add one
  lesson here, correct one wrong memory entry, or prune one stale entry.
- Entry format: `- YYYY-MM-DD | rule | evidence: path | hits: N`.
- A lesson states a reusable behavior change, not a run narrative. Narratives
  belong in `agent-action-log.md`.
- When a run re-confirms an existing lesson, increment its `hits` count and
  update the date instead of adding a duplicate.
- The System Review Loop promotes lessons with `hits >= 3` into durable
  contracts in `LANDMARKS.md` or fixes in the automation prompts, then removes
  them here. It also prunes lessons unused for a full review cycle.

## Active Lessons

- {{DATE}} | Record one concrete, reusable lesson per substantive run; increment hits when a lesson is re-confirmed. | evidence: hub/MEMORY/README.md | hits: 1
