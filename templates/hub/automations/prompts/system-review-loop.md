# System Review Loop

Run a background consolidation pass so the workspace gets a little better
every cycle: lessons feed back into durable behavior, and compact memory
stays within budget.

Required inputs:

1. `hub/MEMORY/LESSONS.md` - active lessons and hit counts.
2. `hub/MEMORY/indexes/memory-health.json` and
   `hub/MEMORY/indexes/memory-health-history.jsonl` - current budgets and the
   trend across runs.
3. Recent reviews under `hub/MEMORY/self-optimization/`.

Required steps:

1. Run preflight, sync, memory index, state digest, memory health, and
   package gates where relevant.
2. Consolidate lessons:
   - Promote lessons with `hits >= 3` into a durable contract in
     `hub/MEMORY/LANDMARKS.md` or a concrete fix to the automation prompt or
     script that keeps causing the lesson, then remove them from
     `hub/MEMORY/LESSONS.md`.
   - Prune lessons that were never re-confirmed since the last review cycle;
     note the pruning in the review.
3. Enforce memory budgets:
   - Review the rotation plan from
     `python3 hub/scripts/memory_compact.py --root .` and run it with
     `--execute` when the action log is over budget.
   - Trim stale `Top Of Mind` entries in `LANDMARKS.md`, moving anything
     still useful into the action log or a dated report.
4. Review stale blockers, missing metadata, incomplete work packages, memory
   drift, automation debt, and repeated manual work. Repeated manual work is
   a candidate for a new lesson or automation change.
5. Stay inside admin surfaces unless a work-item change is clearly safe and
   necessary.
6. Exit gate: `python3 hub/scripts/memory_health.py --root . --write --strict`
   must pass. Fix violations before closing.
7. Write a dated review under `hub/MEMORY/self-optimization/` that records
   what was promoted, pruned, rotated, and fixed, plus the health trend
   compared with the previous review.
8. Close with what changed, what was learned, and what needs the operator's
   decision.
