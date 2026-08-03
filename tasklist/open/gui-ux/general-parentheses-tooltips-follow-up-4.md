Title: I hovererd over everything multiple seconds and not a single tooltip showed up
Prio:  1

Goal:  Follow-up from general-parentheses-tooltips-follow-up-3: even after hovering many fields for
       several seconds in the locally-built gui.exe, no tooltip appears anywhere, despite that
       investigation confirming the Qt tooltip mechanism (qwindows.dll, Qt6Widgets.dll, Qt6Gui.dll,
       style.qss's QToolTip rule) is bundled correctly and no frozen-specific code path in
       main.py/widgets.py suppresses tooltips. Three prior investigations (general-parentheses-
       tooltips-follow-up, -follow-up-2, -follow-up-3) each ruled out a structural/packaging cause;
       this one needs to pivot to the user's own live environment instead of re-reading the same
       code again.
Files: gui/app/style.qss (QToolTip rule, already verified byte-identical in the build), gui/app/
       widgets.py (CheckmarkProxyStyle, already confirmed to have no event()/eventFilter()/
       styleHint() override that could intercept QEvent::ToolTip), gui/app/main_window.py
       (installEventFilter is only ever attached to the settings-search popup, not app-wide, so it
       cannot be the cause), gui/pyproject.toml (PySide6>=6.7.0, unpinned - the one variable the
       prior round could not close without a live build).
Steps: 1. Ask the user directly (AskUserQuestion is available now, unlike in the prior round) for
          the exact PySide6 version their build resolved (`pip show PySide6` in gui/.venv) and
          whether they are certain they are hovering the freshly built exe rather than a stale
          running instance or an old Start Menu shortcut.
       2. Have the user try the same hover test on a plain `python -m app.main` source run (not the
          frozen exe) to isolate whether this is frozen-build-specific after all, since the last
          round's static analysis found no frozen-specific code path but could not run the actual
          binary.
       3. Have the user check Windows's own tooltip/hover settings are not the cause (Windows
          "Show tooltips" accessibility setting, or ClickLock/pointer-hover delay set unusually
          high), since three rounds of code-level investigation found nothing in this repository
          that could suppress ToolTip events app-wide.
       4. If a PySide6 version mismatch turns out to be the cause, pin an exact working version in
          gui/pyproject.toml instead of the current `>=6.7.0` range.
Open:  -
