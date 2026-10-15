# Operator System Architecture

The starter kit renders portable templates into a workspace. Configuration names
an organization and its adapters; source evidence and user authority remain local.

## Components and ownership

| Component | Responsibility |
| --- | --- |
| `AGENTS.md` | Concise authority, context selection, evidence, and closeout policy |
| `hub/config/org.json` | Paths, capabilities, adapter commands, schedules, budgets |
| `hub/automations/` | Task-specific prompts and acceptance-check names |
| `hub/MEMORY/` | Durable facts, reports, lessons, and run/delivery records |
| `work-items/` | Canonical sources, mappings, decisions, and outputs |
| `knowledge-base/` | Reusable procedures |
| `local-private/` | Ignored private material |

## Preparation

`ops observe` validates configuration without generated-state writes.
`ops prepare --repo <path>` checks selected write dependencies and requested
capabilities. `ops startup` performs the full maintenance refresh. Scope failures
block affected writes; existing dirt is preserved, and automatic stashing is disabled.

Shared instructions come from `operator_common.run_contract()`. Installed bundles
and runtime packets use that function instead of repeating mandatory startup and
learning recipes in every prompt. Lessons are retrieved when relevant.

## Run lifecycle

1. Generate a unique packet with the objective, source references, permitted scope,
   exact run ID, and acceptance-check names.
2. Optional invocation passes the packet on stdin, sets the workspace directory,
   and records start/process exit separately from task completion.
3. The agent performs authorized work and validates its result.
4. Closeout requires evidence and named passing checks for success/no-op, or a
   concrete blocker/next action for partial, blocked, or failed work.
5. A process exit of zero without a matching valid chained close returns runner
   exit code 3. Process failures keep their nonzero exit code.

Closeout is idempotent under a process lock. Amendments are explicit, revisioned
receipts. New receipts cover the full record in a hash chain. Atomic file replacement
prevents partially written JSON; retry can rebuild close.json after a chain commit.
Older hash-chain entries remain readable without claiming new-format guarantees.

## Delivery lifecycle

Outbox IDs persist across retries. A per-ID lock and durable reservation precede
external execution. Acknowledged sends reuse their existing receipt. Uncertain
results require destination reconciliation; verified absence allows an explicit
retry. Historical executed receipts are consulted before the first new reservation.
This avoids automatic duplicate sends; it does not promise transactional exactly-once
semantics across third-party services.

## Evidence and memory

The generic evidence gate validates nonempty inputs, labeled owner/request/boundary
context, and unambiguous source-map coverage. A structure-only profile supports
intake without implying readiness. Domain-specific validation remains required.

Learning is optional. Exact rules can receive new evidence; near matches are
review candidates, not confirmations. Evidence references are deduplicated. Rules
are promoted for demonstrated benefit and removed for a supported reason.
`none` improvements and `no_op` outcomes are healthy.

## Health and interfaces

Health separates packet, start, close, and successful-completion timestamps. Numeric
cron schedules use their IANA timezone and grace period, rather than an inferred
multi-day gap. Explicit legacy max-gap overrides remain supported.

Model profiles select GPT-6 Astra through Codex CLI or Opus 5.5 through Claude
Code. Explicit run overrides precede per-automation routes and workspace defaults;
the existing command wrapper remains the fallback when no profile is selected.
Profile validation and local CLI checks precede invocation. The requested profile
is retained with the packet and invocation receipt; evidence-backed closeout still
determines completion. See [MODEL-PROFILES.md](MODEL-PROFILES.md).

Scheduler exports remain draft packet generators. Live scheduler execution
bindings, bounded continuation, and comparative model evals remain separate work.
No model quality or speed improvements are claimed by the fixture tests.

## Distribution

Scaffolding records file hashes and the kit version. Upgrades add missing templates
and replace unchanged ones, while reporting conflicts and preserving user-owned
memory/admin records. Migration notes identify obsolete policy language that needs
review in those retained records. The starter kit stays independent of any lab's
private data or scientific conventions.
