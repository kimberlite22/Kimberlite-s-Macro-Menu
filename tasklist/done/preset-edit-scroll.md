Title:     man soll im preset edit window runterscrollen sollen
Completed: 2026-07-30
Commit:    2993000

Result: gui/app/edit_preset_window.py wraps the editor in a QScrollArea with setWidgetResizable(True),
covered by gui/tests/test_edit_preset_window.py.
