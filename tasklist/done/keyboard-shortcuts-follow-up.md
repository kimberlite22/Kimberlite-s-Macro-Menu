Title:     ok but remove the big questionmark in the confirm window
Completed: 2026-08-02
Commit:    abe3c5d

Result: Replaced QMessageBox.question() with explicit QMessageBox instances configured with Icon.NoIcon in _delete_step and _delete_screen methods, removing the large question-mark icon from delete-confirmation dialogs while preserving text, buttons, and behavior.
