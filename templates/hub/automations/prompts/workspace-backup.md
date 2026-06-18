# Workspace Backup

Back up the workspace to the configured destination and verify critical paths.

Rules:

1. Confirm the source workspace contains `AGENTS.md`, `hub/`, `work-items/`, and
   `knowledge-base/`.
2. Test destination access before copying.
3. Use a transport appropriate to the organization config.
4. Verify required paths at the destination after transfer.
5. Use `hub/scripts/backup_verify.py` to write the source/destination
   verification report.
6. Use `hub/scripts/backup_transfer.py` first as a dry-run plan; pass
   `--execute` only after confirming the destination and exclusions.
7. Report failed steps explicitly; never describe an unverified backup as
   complete.
