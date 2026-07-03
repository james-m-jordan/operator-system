# Receipt Packet Assembly

Assemble local private evidence packets for receipts, invoices, and charge
support.

Rules:

1. Start from a current request; end quietly when no current request exists.
2. Search broadly enough to find source evidence.
3. Preserve original files and source message text.
4. Write a local packet README with an evidence table and caveats.
5. Keep packet contents under `local-private/` and out of git.
6. Record only non-sensitive memory and unresolved judgment calls.

Closeout ratchet: read `hub/MEMORY/LESSONS.md` before acting. Before ending,
log the run, leave one improvement (lesson, correction, or pruning), refresh
memory health, and close the run record with `hub/scripts/run_close.py`.
