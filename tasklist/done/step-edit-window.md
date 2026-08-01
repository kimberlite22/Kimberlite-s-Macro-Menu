Title:     Die step edit settings in ein neues window machen
Completed: 2026-08-01
Commit:    -

Result: The "Step Editor" group box moved out of Edit Preset into its own non-modal
Step Editor window (gui/app/step_edit_window.py), opened by double-clicking a step row, a new
"Edit Step..." button, or "Add Step" (empty); one instance is reused across clicks so it never
force-closes and reopens, and it has its own Save/Cancel (Update Selected removed). Confirmed
MainWindow.closeEvent's existing top-level-widget sweep already reaches the new window and
anything it opens, arbitrarily nested, with no change needed.
