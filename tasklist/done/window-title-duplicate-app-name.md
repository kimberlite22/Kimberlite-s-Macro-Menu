Title: ok but it currently says: Kimberlites macro menu v0.4.16 (local build) -  Kimberlites macro
       menu. As you can see kimberlites macro menu is twice. Not sure if intended or only on locally
       built versions but if not remove the redundant second time
Completed: 2026-08-12
Commit:    e1d409a

Result: Dropped the setApplicationDisplayName(APP_NAME) call in gui/app/main.py, whose display name
        Qt appends as " - <display name>" to every top-level window title that does not already end
        with it; titles now show exactly what each window sets, on release builds and secondary
        windows too.
