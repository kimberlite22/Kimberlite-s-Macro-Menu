Title: Im running a locally built .exe
Prio:  1

Goal:  Follow-up from general-parentheses-tooltips-follow-up-2: the user confirmed they are running
       a locally built .exe (not an installed release, not `python app/main.py` from source) and
       still see no tooltips; investigate with that specific build path now identified, since the
       prior round ruled out the tooltip mechanism itself and the app-wide TextSelectableByMouse
       change via source-level tests, but could not reproduce a frozen-build-specific difference
       because the build type was unknown at the time.
Files: gui/BUILD.md (how a local build differs from CI's), gui/app/main.py (QApplication/style
       setup), gui/app/widgets.py (CheckmarkProxyStyle and other tooltip-relevant style overrides),
       whatever PyInstaller spec/invocation a local `pyinstaller` build actually uses vs. what
       .github/workflows/release.yml or build-exe.yml run in CI, the labels carrying tooltips from
       general-parentheses-to-tooltips (commit e15ddd4).
Steps: 1. Build gui.exe locally following gui/BUILD.md exactly and diff the resulting PyInstaller
          invocation/spec against what release.yml/build-exe.yml actually run, looking for a flag or
          bundled-data difference (missing Qt plugin, different Qt style) that could suppress
          tooltips only in a frozen build, not in a source run.
       2. Launch the locally built exe (not source) and manually verify whether tooltips are missing
          across the board or only for specific fields, narrowing whether this is a global Qt
          platform/style issue in the frozen build or a field-specific regression.
       3. If reproduced, bisect: does a source run (`python app/main.py`) with the exact same
          PySide6/Qt version installed as the frozen build reproduce it too? If yes, this is a
          code/version issue, not a packaging one, and the earlier source-level tests missed it only
          because they ran against a different installed Qt version.
       4. If not reproduced even with a fresh local build, ask the user for exact repro steps (which
          field, hover duration, whether any tooltips work at all) since the report may point at a
          stale local build rather than current main.
Open:  -
