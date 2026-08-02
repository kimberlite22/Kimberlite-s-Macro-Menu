Title:     Normalerweise ist bei feldern der text dann doppelpunkt und dann das feld. Remove den
           doppelpunkt.
Completed: 2026-08-02
Commit:    -

Result: Every label-then-field form row across gui/app/*.py (QFormLayout.addRow calls and the
        equivalent _add_editor_row/_add_row helpers in step_edit_window.py and
        map_advanced_window.py, plus the manually built label-then-field rows in main_window.py) no
        longer has a trailing colon; standalone/status labels ("Search:", "Runs on Start: -",
        "Agent: ...") were left untouched, out of scope.
