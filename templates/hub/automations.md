# Automation Catalog ({{WORKSPACE_NAME}})

This catalog lists portable recurring automations for `{{ORG_NAME}}`. Each
automation should read compact memory first, act from current evidence, and end
with the required memory and repo hygiene closeout.

Install machine-readable automation specs from the manifest with:

```bash
python3 hub/scripts/install_automations.py --root . --out .operator-automations
```

## Morning Control Panel

Purpose: Build a daily operator brief from email, chat, calendar, tasks, and
current workspace state.

Inputs:

- recent inbox and chat messages
- current-day calendar
- task or issue queue
- `hub/MEMORY/state-digest.md`
- prior dated morning folder, when present

Outputs:

- `hub/MEMORY/morning/YYYY-MM-DD/morning-brief.md`
- `hub/MEMORY/morning/YYYY-MM-DD/action-queue.md`
- draft replies or decision notes under the dated folder
- one concise status post to `{{PRIMARY_STATUS_CHANNEL}}`, when configured

Rules:

- Draft external replies instead of sending them unless approval is explicit.
- Prioritize decisions, blockers, deadlines, and commitments.
- Link committed artifacts rather than local-only paths in status posts.

## Chat Intake And Action Turn

Purpose: Convert authorized chat requests and file uploads into completed work,
follow-up tasks, or clarification replies.

Inputs:

- exact trigger flags such as `<<AGENT>>`
- direct asks to the operator agent
- recent source threads and uploaded files
- issue/task queue and prior automation memory for dedupe

Outputs:

- same-thread replies for acted-on items
- committed work-item files or issues/tasks
- action-log entries for substantive changes

Rules:

- Read full thread context before acting.
- De-duplicate against prior replies, commits, issues/tasks, and memory.
- Preserve real file bytes when files are part of the work.
- Apply the work package gate before analysis or transformation.
- End quietly when nothing actionable exists and the workflow allows it.

## External Feed Digest

Purpose: Watch external feeds and post a deduped digest to the configured
knowledge or alerts channel.

Inputs:

- official feeds, APIs, newsletters, or saved searches
- prior digest memory
- topic filters from `hub/config/org.json`

Outputs:

- a concise digest post or markdown report
- updated automation-local memory with source IDs and links

Rules:

- De-duplicate by stable IDs, URLs, DOIs, ticket IDs, or feed GUIDs.
- Prefer primary sources.
- State verification limits when metadata is incomplete.

## Opportunity Planning Refresh

Purpose: Maintain a current list of conferences, grants, submissions,
procurement windows, launches, renewal dates, or other opportunity deadlines.

Inputs:

- official opportunity pages or internal trackers
- current work-item readiness
- people/work-item bios

Outputs:

- refreshed opportunity memo
- status post to the configured channel
- action-log and comms memory entries when priorities change

Rules:

- Verify dates from official sources before posting.
- Mark stale or unverified deadlines explicitly.
- Connect opportunities to work-item readiness instead of generic interest.

## System Review Loop

Purpose: Periodically consolidate lessons into durable behavior, enforce
memory budgets, and inspect the workspace for stale blockers, missing memory,
incomplete packages, repo hygiene issues, and opportunities to reduce future
rework.

Inputs:

- state digest
- memory indexes, including `memory-health.json` and the health history
- `hub/MEMORY/LESSONS.md` hit counts
- recent `hub/MEMORY/self-optimization/` reviews
- automation catalog
- recent sync reports
- work-item blockers

Outputs:

- promoted lessons (into `LANDMARKS.md` contracts or prompt/script fixes) and
  pruned stale lessons
- action-log rotation via `memory_compact.py` when over budget
- self-review report with the health trend versus the prior review
- package-risk or blocker queue
- concise admin summary with decisions needed

Rules:

- Stay inside admin-owned surfaces unless a work-item change is clearly safe and
  necessary.
- Archive inactive report systems instead of creating new root-level clutter.
- Add only current behavior pointers to `LANDMARKS.md`.
- Close only after `memory_health.py --write --strict` passes.

## Operations Checklist Scan

Purpose: Keep a recurring checklist in sync with completion evidence from chat,
forms, issues, or commits.

Inputs:

- checklist file in `knowledge-base/operations/`
- recent completion evidence from configured channels or trackers

Outputs:

- updated checklist when evidence supports it
- status post with completed and remaining items

Rules:

- Treat ambiguous notes as unresolved.
- Preserve issue/problem notes.
- Commit only checklist changes in the owning repo or folder.

## Workspace Backup

Purpose: Back up the full workspace to a configured remote destination and
verify that critical surfaces arrived.

Inputs:

- source workspace path
- backup destination and transport config
- exclude list

Outputs:

- verified backup
- status post or issue report
- backup memory entry with route and size summary

Rules:

- Test destination write access before copying.
- Verify `AGENTS.md`, `hub/`, `work-items/`, and `knowledge-base/`.
- Report failed backup steps explicitly.

## Receipt Packet Assembly

Purpose: Assemble private receipt, invoice, or evidence packets from email and
local exports without committing private artifacts.

Inputs:

- current request from email, chat, or task system
- matching receipts, invoices, confirmations, or source messages

Outputs:

- local ignored packet under `local-private/`
- packet `README.md` with evidence table and caveats
- durable non-sensitive memory entry

Rules:

- Search broadly enough to find source evidence.
- Preserve original files.
- Keep private packet contents out of git.
- Surface unresolved matches and amount/date mismatches.

## Chat File Intake

Purpose: Move authorized chat file uploads into the canonical work item with
preserved bytes and recorded metadata.

Inputs:

- trigger message and thread context from `{{INTAKE_CHANNEL}}`
- fetched file bytes under ignored `local-private/` storage
- target work-item id and metadata answers from the requester

Outputs:

- preserved source file under `work-items/<id>/source/chat-uploads/`
- metadata record under `work-items/<id>/metadata/`
- task draft when the package remains incomplete

Rules:

- Fetch with `chat_file_fetch.py` into `local-private/` before any canonical
  intake.
- Preserve original bytes; never re-encode or rename away provenance.
- Require metadata for every source-bearing file before analysis.
- Create a task draft instead of running partial analysis on an incomplete
  package.
