# Chat File Intake

Route chat-uploaded files into canonical work-item packages.

Rules:

1. Read full source message/thread context before routing a file.
2. Preserve actual file bytes; do not infer content from filenames.
3. If the file is hosted by a chat provider and not already local, use
   `hub/scripts/chat_file_fetch.py` to fetch the bytes into ignored
   `local-private/chat-downloads/` first.
4. Use `hub/scripts/chat_file_intake.py` to copy files into
   `work-items/<id>/source/chat-uploads/` and write metadata.
5. Ask a clarification question before creating or choosing a work item when the
   destination is unclear.
6. Run `hub/scripts/package_gate.py`; if the package is blocked, use
   `hub/scripts/task_draft.py` for the missing metadata or context.

Closeout ratchet: read `hub/MEMORY/LESSONS.md` before acting. Before ending,
log the run, leave one improvement (lesson, correction, or pruning), refresh
memory health, and close the run record with `hub/scripts/run_close.py`.
