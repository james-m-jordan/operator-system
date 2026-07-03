# Morning Control Panel

Build a dated operator brief from current compact memory, email, chat, calendar,
tasks, and open work-item state.

Required sequence:

1. Read `AGENTS.md`, `hub/MEMORY/state-digest.md`,
   `hub/MEMORY/capabilities.json`, `hub/MEMORY/LANDMARKS.md`, and admin docs.
2. Run the generated helper refresh.
3. Triage current messages and commitments.
4. Draft replies and deliverables instead of sending external messages unless
   approval is explicit.
5. Write dated markdown under `hub/MEMORY/morning/YYYY-MM-DD/`.
6. Commit tracked hub artifacts and post one concise status update when
   configured.

Closeout ratchet: read `hub/MEMORY/LESSONS.md` before acting. Before ending,
log the run, leave one improvement (lesson, correction, or pruning), refresh
memory health, and close the run record with `hub/scripts/run_close.py`.
