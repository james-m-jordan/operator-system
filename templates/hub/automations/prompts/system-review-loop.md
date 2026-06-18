# System Review Loop

Run a background review of workspace health and future leverage.

Required checks:

1. Run preflight, sync, memory index, state digest, and package gates where
   relevant.
2. Review stale blockers, missing metadata, incomplete work packages, memory
   drift, automation debt, and repeated manual work.
3. Stay inside admin surfaces unless a work-item change is clearly safe and
   necessary.
4. Write a dated review under `hub/MEMORY/self-optimization/`.
5. Close with what changed, what was learned, and what needs the operator's
   decision.
