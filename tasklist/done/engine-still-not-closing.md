Title:     not working correctly, postpone until later release
Completed: 2026-08-03
Commit:    -

Result: The lingering process was gui.exe itself (the Python/Qt process), not the AHK engine the
two earlier fixes addressed. Two independent gaps in MainWindow.closeEvent (gui/app/main_window.py):
(1) the top-level-widget sweep called isVisible()/close() on each widget with no exception
handling, so one already-deleted widget (its underlying C++ object gone) raised RuntimeError and
aborted the loop, leaving every widget after it in the list unclosed; (2) even with every window
closed, the process still relied entirely on Qt's own quitOnLastWindowClosed noticing the visible
count reached zero, rather than closeEvent stating outright that closing the main window quits the
app. Fixed both: the sweep now tolerates a RuntimeError per widget instead of aborting, and
closeEvent explicitly calls QApplication.instance().quit() once its own close is accepted. Two new
regression tests in gui/tests/test_main_window.py assert both behaviors directly (one confirmed to
fail without the fix, by stashing it and re-running).
