Title:     wenn man die application schließt soll sie nicht mehr im hintergrund laufen
Completed: 2026-07-31
Commit:    -

Result: Closing the main window now stops the AutoHotkey engine in both cases that used to leave
it running: an engine this launch merely attached to (not spawned) is now stopped by PID via a new
`get_engine_pid()`/`stop_engine_by_pid()` pair in engine_process.py wired into `aboutToQuit`; and
`MainWindow.closeEvent` now closes any still-open Edit Preset / Map Advanced / Remote Agent windows
first, since those non-modal QDialogs were each their own top-level widget keeping Qt's
`quitOnLastWindowClosed` from ever firing when only the main window was closed.
