# External Feed Digest

Create a concise deduped digest from configured external feeds or searches.
Read the source URLs and topic filters from the `feeds` block in
`hub/config/org.json` (`feeds.sources`, `feeds.topics`).

Rules:

1. Prefer primary sources.
2. De-duplicate by stable IDs, URLs, GUIDs, ticket IDs, or DOIs.
3. Record the checked source window and any source caveats.
4. Post or save only the useful delta, not the entire feed.
5. Update automation memory with newly seen stable IDs.

Closeout ratchet: read `hub/MEMORY/LESSONS.md` before acting. Before ending,
log the run, leave one improvement (lesson, correction, or pruning), refresh
memory health, and close the run record with `hub/scripts/run_close.py`.
