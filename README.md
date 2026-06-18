# Operator System Starter Kit

This folder is the first distributable, organization-neutral form of the
`lia-live` operating system. It keeps the useful architecture from the current
workspace while removing Jordan Lab and biology-specific assumptions.

The target user is an operator, principal, founder, program lead, or small team
that wants an agent-operated workspace with:

- a hub for admin policy, memory, automation specs, and cross-work synthesis
- work repositories or folders that hold canonical task packages
- structured memory that survives across agent sessions
- recurring automations for inbox triage, chat intake, planning, system review,
  operations checklists, backups, feed digests, and receipt packets
- explicit permission boundaries between admin control surfaces and team work
- clean repo hygiene, run logs, and distributable prompts

## Current Status

This is a packaged starter kit, not a hosted application. It contains:

- `BLUEPRINT.md` - the generalized system architecture and current porting map
- `COMPLETION-MATRIX.md` - the generated release audit matrix
- `config/org.example.json` - an example organization config
- `templates/` - organization-neutral starter files
- `scripts/scaffold_workspace.py` - a standard-library scaffold command
- generated helper scripts for preflight, sync reporting, memory indexing,
  state digest refresh, work-package gating, automation installation, task
  drafting, backup verification, backup transfer, chat-file fetch/intake,
  runtime adapter export, run packet creation, outbox status publication, and
  optional outbox delivery
- `INSTALL.md`, `MIGRATION.md`, and `RELEASE-CHECKLIST.md` - operator setup,
  migration, and packaging checklists
- `scripts/package_release.py` - builds a versioned tarball plus checksum
  manifest for handoff
- `tests/` - smoke tests for the scaffold command

## Quick Start

Preview the generated workspace in a throwaway path:

```bash
python3 hub/distribution/operator-system/scripts/scaffold_workspace.py \
  --config hub/distribution/operator-system/config/org.example.json \
  --out /tmp/operator-system-demo \
  --force
```

Run the smoke tests:

```bash
python3 -m unittest hub/distribution/operator-system/tests/test_scaffold_workspace.py
python3 hub/distribution/operator-system/scripts/audit_release.py --json
python3 hub/distribution/operator-system/scripts/package_release.py --out /tmp/operator-system-release
```

After scaffolding, the generated workspace can refresh its own startup state:

```bash
cd /tmp/operator-system-demo
python3 hub/scripts/preflight_capabilities.py --root .
python3 hub/scripts/sync_workspace.py --root .
python3 hub/scripts/memory_index_refresh.py --root . --write --validate
python3 hub/scripts/state_digest.py --root .
python3 hub/scripts/install_automations.py --root . --out .operator-automations
python3 hub/scripts/export_runtime_adapters.py --root .
python3 hub/scripts/run_automation.py --root . --automation-id morning-control-panel
python3 hub/scripts/publish_status.py --root . --publisher status --message "Ready for review"
python3 hub/scripts/deliver_outbox.py --root . --publisher status --latest
python3 hub/scripts/backup_transfer.py --root . --write-report
printf 'example upload\n' > /tmp/operator-upload.txt
python3 hub/scripts/chat_file_fetch.py --root . --provider direct-url --url file:///tmp/operator-upload.txt
```

See `INSTALL.md` for the full bootstrap flow and `MIGRATION.md` for bringing an
existing workspace into this structure.

## Distribution Boundaries

This package should remain independent of the live Jordan Lab data model:

- Use `work-items/` instead of `team-projects/`.
- Use people/work-item bios instead of trainee/project bios.
- Use general package gates instead of biology assay gates.
- Keep connector names configurable.
- Keep private/local artifacts ignored by default.
- Treat all generated files as starting points that downstream organizations
  can edit for their own policies.

## Optional Follow-Up Adapters

The release audit passes for the portable starter kit. Future adapters can
extend the generic command/webhook/local-copy interfaces when an organization
needs deeper native integrations:

- provider-native scheduler/publisher plugins beyond cron, GitHub Actions,
  webhook, command, and GitHub-issue adapters
- richer issue/task publisher integrations for Linear, Jira, or email
- cloud-storage-specific backup adapters beyond local-copy and rsync
- polished provider-specific chat file recipes beyond direct URL, Slack Web API,
  and command adapters

Those adapters should read an org config rather than hard-coded paths, repo
names, Slack channels, or lab-specific metadata fields.
