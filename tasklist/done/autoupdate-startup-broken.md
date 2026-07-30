Title:     Das Autoupdate beim starten der application ist broken
Completed: 2026-07-31
Commit:    0c9c655

Result: gui.exe now offers, downloads, verifies (sha256) and installs a newer release on startup via
a detached replace-and-relaunch helper, replacing the notice-only check.
