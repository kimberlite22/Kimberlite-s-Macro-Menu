Title:     not working
Completed: 2026-07-31
Commit:    -

Result: main_window.closeEvent now closes every visible top-level widget instead of only the
three tracked window collections, so a window nested a level deeper (EditPresetWindow's Option
Availability picker, shown independently via .open() and never closed by its parent) can no
longer keep the process alive after the user closes the main window.
