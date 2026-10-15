# Release verification

1. Inspect the run-owned diff and version/changelog. Preserve unrelated work.
2. Compile all scripts and run the entire test suite:

```bash
python3 -m compileall -q scripts templates/hub/scripts tests
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/audit_release.py --write COMPLETION-MATRIX.md
python3 scripts/demo_walkthrough.py
python3 scripts/package_release.py --out /tmp/operator-system-release
```

3. Review regression coverage for scoped preparation, preserved dirty repos,
   empty/ambiguous packages, opposing lessons, repeated evidence, success without
   closeout, repeated/amended closeout, concurrent delivery, uncertain retries,
   schedule/DST boundaries, safe workspace upgrades, profile selection/validation,
   both provider CLI fixtures, incompatible runtimes, and worker timeout cleanup.
4. Inspect the release archive and checksum manifest. Confirm it excludes private
   data, Git metadata, bytecode, and temporary test outputs.
5. Inspect migration guidance and confirm existing memory/admin files are preserved.
6. Commit only run-owned paths, push the requested branch, and verify the remote
   commit and final working-tree/stash state. Tag/publish only if authorized.

The release audit checks distributable structure. Fixture tests do not prove live
model performance, connector access, or scheduler deployment. Record those limits.
