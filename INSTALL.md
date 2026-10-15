# Install and operate

Requires macOS or Linux, Python 3.10+, and Git. The kit uses the standard library
and POSIX process locks. Scaffolding installs no credentials or live schedules.

## Create a workspace

Edit a copy of `config/org.example.json`: organization, workspace, roles, paths,
required capabilities, providers, and desired schedules. Keep credentials in the
configured environment variables, not JSON or Git.

```bash
python3 scripts/scaffold_workspace.py --config config/org.example.json --out /tmp/operator-demo
cd /tmp/operator-demo
python3 hub/scripts/ops.py observe
```

`observe` reads configuration only. For a scoped change:

```bash
python3 hub/scripts/ops.py prepare --repo hub --repo work-items/example
```

Select existing repositories or folders. Add `--capability github_cli`,
`--capability env:VARIABLE`, or `--capability command:executable` when required.
Default checks are Python and Git. Connector availability must be verified through
its owning runtime. Preparation fetches only selected repo dependencies and makes
no generated-state writes. Stale, divergent, or inaccessible repos block dependent
writes. Dirty behind repos require explicit reconciliation; no automatic stash.

For initial full setup or broad maintenance:

```bash
python3 hub/scripts/ops.py startup
```

This validates config, refreshes capabilities, checks repo freshness, and rebuilds
indexes, digest, and health. It stops on failed prerequisites.

## Task packets and agent invocation

```bash
python3 hub/scripts/ops.py run morning-control-panel
```

This creates a packet, without executing it. Its printed path contains the run ID.
Every automation has named acceptance checks (default `output_verified`), and
receives one shared run contract. Task prompts contain only task-specific guidance.

Configure `runtime.agent_command` as an argv list for your selected runtime or
wrapper. It receives packet text on stdin, runs from the workspace directory, and
gets `OPERATOR_RUN_ID`, `OPERATOR_WORKSPACE`, and `OPERATOR_PACKET` in its environment.
Arguments containing `{packet}` receive the packet's absolute path. A wrapper must
actually execute the packet and perform closeout; passing a filename is not an
implicit file-input protocol. The example echo command is deliberately not a real
agent and cannot produce successful completion.

```bash
python3 hub/scripts/ops.py run morning-control-panel --invoke
```

The worker closes the exact run ID after validation:

```bash
python3 hub/scripts/run_close.py --run-id <run-id> --outcome success \
  --evidence outputs/result.md --check output_verified=pass
```

Use `no_op` for a complete quiet scan with source-coverage evidence. No lesson is
required. `partial`, `blocked`, and `failure` require `--note` with the blocker and
next action. Optional `--lesson` requires an evidence reference. Identical closes
are idempotent; changed closes require `--amend --note`. `--latest` is retained for
interactive compatibility and refuses multiple open runs.

An exit-zero process with incomplete or invalid closeout returns runner code 3.
`started.json`, `invoke.json`, and `close.json` distinguish execution from task
completion. The runner verifies that closeout matches its chained receipt.

## Outbox and delivery

Create an outbox item using `publish_status.py`. Inspect the resulting message and
its configured destination. Configuration alone grants no send authority.

```bash
python3 hub/scripts/publish_status.py --publisher status --message 'Ready for review'
python3 hub/scripts/deliver_outbox.py --outbox-item <exact-json-path>
```

Dry run writes a receipt without sending. With existing send authority, pass
`--execute` and optionally `--run-id`. Repeated delivery of the same item reuses a
confirmed receipt. A timeout or uncertain result blocks automatic retry.

After inspecting the destination, record the result:

```bash
python3 hub/scripts/deliver_outbox.py --outbox-item <exact-json-path> \
  --resolve delivered --evidence <verified-destination-reference>
```

Use `--resolve not-delivered` only after verifying absence; a later explicit
`--execute` may then retry. Changed content under a reserved ID is rejected.
Delivery reservations persist beyond normal receipt retention.

## Evidence gates and schedules

Run `package_gate.py --work-item work-items/<id>` before analysis. The default
profile validates nonempty sources/metadata, labeled owner/request/boundary fields,
and unambiguous mappings for every source. CSV/TSV mappings use a file column and
meaning column; JSON may use an array of equivalent row objects. Intake provenance
alone does not establish the meaning of an uploaded file. See README for aliases.

`--profile structure` checks intake structure only. Validate domain assumptions,
methods, row-level mappings, and claims separately.

Schedule health supports numeric lists, ranges, and steps in five-field cron
expressions, with IANA timezones and `grace_minutes` (default 15). It measures
successful/no-op completion separately from packet creation and process start.

```bash
python3 hub/scripts/install_automations.py
python3 hub/scripts/export_runtime_adapters.py
```

These commands write reviewable specs and packet-only scheduler drafts. They do
not register a scheduler or execute a model. Before deployment, bind the selected
runtime, arrange durable artifacts, and reconcile the draft's scheduler timezone
with the configured timezone; the draft exports do not implement that binding.

## Verification

`ops doctor` reads health and maintenance plans; `ops verify` checks close receipts.
Run `scripts/demo_walkthrough.py` from the kit for an offline end-to-end fixture.
Live provider/model evaluation and scheduler installation are separate activities.
