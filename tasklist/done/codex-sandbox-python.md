Title:     add python to codex
Completed: 2026-08-07
Commit:    eded325

Result: Delegated Codex runs can now execute the project's pytest suites; the gui suite reports the
same 410 passed inside the sandbox as it does locally. The cause was never a missing interpreter:
Codex's sandbox runs as a separate OS account that could not read the Python under the launching
user's profile, and then could not use that user's %TEMP% either. The per-machine permission grants
are documented in CLAUDE.md ("Letting Codex run the test suites"); the committed half is
tools/codex-delegate.mjs pointing the codex child's TEMP/TMP/TMPDIR at a profile-independent temp
directory, best-effort so a machine without the setup is unaffected.
