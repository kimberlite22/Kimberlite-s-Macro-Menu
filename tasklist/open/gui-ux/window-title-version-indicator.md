Title: display current version and wether or not this is a local built .exe in the window bar
       above the application window
Prio:  2

Goal:  The main window's title bar (currently just APP_NAME, set via setWindowTitle in
       gui/app/main_window.py) also shows the running app's version (read the same way
       gui/app/update_check.py's read_current_version already does) and whether this is a locally
       built exe versus an official release build (gui/app/launcher_paths.py's is_frozen() plus
       whatever already distinguishes a release build from a local one).
Open:  What should count as "local built" versus "official release" - is there already a reliable
       signal to distinguish the two (e.g. a release-only marker file, a different VERSION
       provenance), or does one need to be added?
Files: gui/app/main_window.py:206 (`self.setWindowTitle(APP_NAME)`, the one call site to change),
       gui/app/update_check.py:169 (`read_current_version(entry_file)`, already resolves bundled
       VERSION first then the repo-root dev VERSION file - reuse as-is), gui/app/launcher_paths.py:30
       (`is_frozen()`, distinguishes a PyInstaller bundle from a source run only; it does NOT
       distinguish a local PyInstaller build from an official CI release build - both set
       `sys.frozen`), `.github/workflows/release.yml` / `tools/build-local-exe.ps1` (the two places
       that invoke PyInstaller; neither currently stamps any release-only marker into the bundle, so
       today there is no existing signal to read for local-vs-release - confirmed by re-reading
       launcher_paths.py and update_check.py end to end, nothing else in gui/app/*.py touches this).
Steps: 1. Resolve the Open question first: since no local-vs-release signal exists yet, the simplest
          option is to add one, e.g. release.yml writes a marker file (or a distinct VERSION suffix)
          next to the bundle that a local build never produces, and read_current_version-style logic
          checks for its presence. Confirm this approach with the user before implementing, since it
          changes the release workflow, not just the GUI.
       2. Once a signal exists, build a small title-string helper (e.g. in launcher_paths.py or
          inline in main_window.py) that composes "APP_NAME vX.Y.Z" plus a "(local build)" /
          "(source)" suffix from is_frozen() plus the new marker, falling back to just APP_NAME if
          read_current_version() returns None (mirrors the existing None-handling pattern already
          used elsewhere for a missing/unparseable VERSION file).
       3. Replace the single `self.setWindowTitle(APP_NAME)` call with the new composed title.
       4. Add/extend a gui/tests/ unit test asserting the title format for each of the three cases
          (official release, local build, source run), following the existing per-window test module
          layout.
