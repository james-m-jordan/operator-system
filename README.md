# Operator System Starter Kit

A portable workspace for an operator, principal, founder, or small team using
capable agents. Canonical work packages, explicit authority, durable memory, and
verifiable run records let work continue across sessions and runtimes.

This is a Python standard-library starter kit for macOS and Linux. It generates
an organization-specific workspace; it is not a hosted service or a live model
integration. The current release is **0.6.0**.

## What the kit provides

- `hub/`: administrative policy, configuration, memory, automations, and reports.
- `work-items/`: canonical source packages, metadata, and outputs.
- `knowledge-base/`: shared methods and reusable references.
- `local-private/`: ignored private evidence and exports.
- Nine automation prompt/spec bundles, a command-based agent runner, scheduler
  drafts, an outbox, backup helpers, and file-intake adapters.
- Safe template upgrades that preserve locally edited files and user-owned memory.

## The operating loop

```text
request or scheduler
        |
        v
run packet: objective + scope + shared contract + acceptance checks
        |
        v
agent: relevant context -> scoped preparation -> authorized work -> verification
        |
        +--> outbox item -> reservation -> delivery receipt
        |                       |
        |                       +--> uncertain result -> reconcile before retry
        v
close record: outcome + evidence + checks + optional learning
        |
        v
periodic review: investigate evidenced friction; retain useful lessons
```

A quiet scan can complete with `no_op` and `improvement=none`. Learning is based
on new evidence, without a quota. Repeated wording and repeated imports do not
establish independent confirmation. Similar-but-different lessons require review.

## Quick start

Requires Python 3.10+ and Git. No extra Python packages are required.

```bash
python3 scripts/demo_walkthrough.py
```

The demo uses a local fixture agent, creates a small output, and closes its run
with evidence. It does not call a model or send a message.

Create a workspace from an edited copy of `config/org.example.json`:

```bash
python3 scripts/scaffold_workspace.py --config config/org.example.json --out /tmp/operator-demo
cd /tmp/operator-demo
python3 hub/scripts/ops.py observe
python3 hub/scripts/ops.py prepare --repo hub
```

Use `ops.py startup` for broad maintenance. Ordinary preparation fetches and
checks selected repositories without a global index/memory refresh; it never
auto-stashes changes. Behind, divergent, or failed dependencies block their
writes. Existing local-only repos can be prepared without a remote.

See [INSTALL.md](INSTALL.md) for runtime setup and [MIGRATION.md](MIGRATION.md)
for existing workspaces.

## Completion and delivery

A run packet is planning state. `--invoke` sends the packet text on stdin to
`runtime.agent_command`, sets the workspace as its working directory, and supplies
`OPERATOR_RUN_ID`, `OPERATOR_WORKSPACE`, and `OPERATOR_PACKET`. `{packet}` in a
command argument remains a path substitution for wrappers that need it.

The example command only prints a setup notice. It does not complete a task;
invoking it returns an incomplete-run exit code. Configure a real runtime before
using unattended execution. Provider-specific model/effort profiles and automatic
continuation are separate follow-up work.

A worker closes its exact run ID:

```bash
python3 hub/scripts/run_close.py --run-id <run-id> --outcome success \
  --evidence outputs/result.md --check output_verified=pass
```

`success` and `no_op` require evidence and all named acceptance checks to pass.
`partial`, `blocked`, and `failure` require a note describing the next action.
These are recorded acceptance results; the generic runner cannot independently
judge the scientific or business correctness of every artifact. Local evidence
must exist and be nonempty; URL evidence must be a verified HTTP(S) reference.

Identical closeout retries reuse the receipt. Changed closeouts require
`--amend --note`. The hash chain covers the complete new receipt, including its
checks and evidence references; `ops.py verify` checks the chain and materialized
receipts. It is not a signature or independent protection against rewriting the
entire ledger.

Outbox delivery reserves a stable ID before sending. A confirmed delivery is
not resent on retry. An interrupted or failed attempt stays uncertain until the
operator checks the destination and records `--resolve delivered` or
`--resolve not-delivered` with evidence. The latter permits a subsequent explicit
retry. Reservations are not expired or removed by retention sweeping.

## Evidence and monitoring

The default package gate checks nonempty files, explicit owner/request/boundary
fields, and CSV/TSV/JSON coverage of every source file. Metadata rows identify a
`file`/`path`/`source_file`/`stored_path` and a `meaning`/`description`/`role`/
`sample`/`sample_id`. Use relative paths when basenames are ambiguous.

`--profile structure` is intake triage only. Domain-specific methods, row-level
metadata, and scientific claims still require their own checks. Indexes say
`ready_for_review` after the generic evidence check, not that analysis is complete.

Schedule health evaluates numeric five-field cron expressions in the configured
IANA timezone, including DST. It tracks packet creation, start, close, and
successful completion separately. The default grace is 15 minutes;
`grace_minutes` is configurable. An explicit legacy `max_gap_hours` overrides
schedule-based freshness. Generated cron/Actions files remain **packet-only
drafts**, not installed or verified live schedules; review their timezone and
runtime binding before deployment.

## Memory and portability

Memory search, compact state, wiki synthesis, and the operator report provide
continuity without rereading all history. Exact lessons are confirmed once per
evidence reference. Review benefit, scope, and counterexamples before promotion;
hit counts are hints, not proof. Rare but valid rules need not be deleted.

Lesson packs carry rules and optional provenance. Evidence references are stripped
by default, but rule text itself can contain private information: review exports
before sharing and imports before activation. Re-importing identical evidence
does not increase confirmation counts.

## Development and release checks

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/audit_release.py --json
python3 scripts/package_release.py --out /tmp/operator-system-release
```

The suite covers scaffolding, upgrades, evidence gates, scoped preparation,
concurrent delivery, interrupted retries, closeout integrity, and schedule health.
The release audit checks distributable structure. Neither replaces live model
behavior evaluations or provider integration tests.

See [BLUEPRINT.md](BLUEPRINT.md), [CHANGELOG.md](CHANGELOG.md), and
[RELEASE-CHECKLIST.md](RELEASE-CHECKLIST.md). Apache License 2.0.
