Title:     Im running a locally built .exe
Completed: 2026-08-03
Commit:    -

Result: Structural investigation, no code change: with the build path now confirmed as a local
        PyInstaller build (not source, not an installed release), compared the actual PyInstaller
        invocation that a local build produces against what CI runs. `tools/build-local-exe.ps1`
        (the VS Code "Build local Windows EXE" task, the most likely thing "locally built .exe"
        refers to), `.github/workflows/build-exe.yml`, and `.github/workflows/release.yml` all
        invoke PyInstaller for the GUI with the exact same flag set (`--windowed --onefile --paths .
        --add-data style.qss;. --add-data VERSION;. --add-binary engine;engine --icon ... --add-data
        icon;. --name gui`); no flag, style, or bundled-data difference exists between them.

        Went further than reading the commands: actually ran `pyinstaller` locally with this exact
        flag set against current `gui/app/main.py` (PyInstaller 6.21.0, PySide6 6.11.1). The build
        succeeded with no missing-module or missing-hook warnings touching Qt/GUI (only harmless
        posix-only stdlib warnings, e.g. `pwd`/`grp`/`fcntl`, expected on Windows). Listed the
        produced `dist/gui.exe`'s embedded archive
        (`python -m PyInstaller.utils.cliutils.archive_viewer -r -l`) and confirmed every plugin the
        tooltip/rendering path depends on is present and correctly bundled: the `qwindows.dll`
        platform plugin (owns the Windows event loop and mouse-move-driven hover detection that
        raises `QEvent::ToolTip`), `Qt6Widgets.dll`, `Qt6Gui.dll`, and `style.qss` itself (byte-
        identical `QToolTip { ... }` rule, same non-degenerate dark-background/light-text colors
        already verified in the prior round).

        Re-read `gui/app/main.py`'s `QApplication`/style setup and `gui/app/widgets.py`'s
        `CheckmarkProxyStyle` end to end for anything frozen-build-specific that could suppress
        tooltips: the only `is_frozen()` branches in `main.py` gate engine self-install/management
        (lines ~221-316), never tooltip, style, or event delivery. `CheckmarkProxyStyle` only
        overrides `polish()` (label selectability) and `drawPrimitive()` (checkbox glyph); it has no
        `event()`, `eventFilter()`, `notify()`, or `styleHint()` override, so `QEvent::ToolTip`
        delivery is untouched and goes straight to Qt's base `Fusion` style/widget handling in both a
        source run and a frozen build. Checked commit c87739f (the one prior style-override revert,
        removing a `drawComplexControl` combo-box-arrow override) for leftover residue: the revert is
        clean, nothing tooltip-adjacent remains. No `QT_QPA_PLATFORM` or other Qt env var is set
        anywhere in production code (only in `gui/tests/conftest.py` and the build scripts' own smoke
        tests), so a frozen launch uses the real `windows` platform plugin, not `offscreen`.

        No structural or packaging cause was found. Combined with the prior round's headless
        QTest-driven proof that the tooltip mechanism is correct on current source, this rules out
        packaging flags, bundled Qt plugins, stylesheet content, and every frozen-specific code path
        as candidates. The remaining unpinned variable is PySide6/PyInstaller version drift: neither
        `gui/pyproject.toml`'s `PySide6>=6.7.0` nor the dev extras pin an exact version, so the
        user's local build could have resolved a different PySide6 minor version than whatever was
        used for the earlier headless probes; that is a real, live-environment-only gap this
        investigation cannot close without launching a built exe and hovering over a field by hand,
        which is out of scope per this task's hard constraint. `AskUserQuestion` was not available in
        this environment to request one-time permission, so per the task's own fallback this closes
        as a documented investigation: no code change, needs a live test from the user (which
        specific field, hover duration, whether any tooltip anywhere works at all, and the exact
        PySide6 version their build resolved via `pip show PySide6`) to make further progress.
