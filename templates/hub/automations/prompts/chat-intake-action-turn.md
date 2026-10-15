# Chat Intake And Action Turn

Convert authorized chat requests into completed work, follow-up tasks, or
clarification replies.

Rules:

1. Prioritize exact trigger flags such as `<<AGENT>>`.
2. Read full thread context before acting.
3. De-duplicate against prior replies, commits, task drafts, and memory.
4. Use `hub/scripts/chat_file_intake.py` for uploaded files when bytes are
   available.
5. Use `hub/scripts/package_gate.py` before analysis or irreversible
   transformation.
6. Use `hub/scripts/task_draft.py` when the package is incomplete or the next
   action belongs to a collaborator.
7. Reply in the originating thread for acted-on items; end quietly when nothing
   actionable exists and the workflow allows it.
