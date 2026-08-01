Title:     in General remove die descriptions in klammern und mach aus denen einfach eine tooltip wenn
           man über den text oder die box hovert, Die können auch gerne dann mehr sagen als nur das was
           in klammer war aber die klammern sollen weg. Mach das mit allen vorkommen von klammern im
           programm.
Completed: 2026-08-01
Commit:    -

Result: Swept gui/app/*.py for static parenthetical label qualifiers and converted each to a
        QWidget.setToolTip(...) call, removing the parentheses from the visible text. Converted 12
        occurrences across 5 files: gui/app/main_window.py (9: "Daily limit (0 = unlimited)",
        "Extra wait after each full cycle (sec):", "Click delay (ms):",
        "Tower placement delay (ms):", "Max cycles (0 = unlimited):",
        "Position marker size (px):", "Default slots (position 1 through 10):", the "Disconnect
        Detection (Auto-Reconnect)" group box title, "Check every (sec):"),
        gui/app/map_advanced_window.py (2: the "Use custom camera/zoom settings..." checkbox and
        the "Drag (ms):" row), gui/app/step_edit_window.py (2: "Drag (ms):" and
        "Wait After (s):"), gui/app/option_availability_window.py (1: the invert checkbox), and
        gui/app/edit_preset_window.py (STEP_TABLE_COLUMNS "Drag (ms)"/"Wait (s)" column headers,
        tooltip set via horizontalHeaderItem). Deliberately left untouched: sentinel/placeholder
        combo values that use parentheses as part of their actual compared-against value
        ("(none)", "(continue)", "(Repeat)", "(Stop Macro)"); dynamic runtime status text built
        from f-strings or branching (update-check notices, IPC ack/error messages,
        map_advanced_window.py's "Editing: shared default (all maps)" /
        "... (all maps without custom settings)" labels, which are chosen per-branch at runtime
        rather than a fixed static label); and remote_agent_tab.py's existing setToolTip() text,
        which already followed this convention and is not a visible label. `python -m pytest
        gui/tests/ -q` passes (228 tests).
