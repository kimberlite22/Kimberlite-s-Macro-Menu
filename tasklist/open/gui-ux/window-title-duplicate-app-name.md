Title: ok but it currently says: Kimberlites macro menu v0.4.16 (local build) -  Kimberlites macro
       menu. As you can see kimberlites macro menu is twice. Not sure if intended or only on locally
       built versions but if not remove the redundant second time
Prio:  5

Goal:  Follow-up from window-title-version-indicator: the main window's native title bar shows the
       app name twice ("<build_window_title() text> - Kimberlite's Macro Menu") instead of the plain
       "Kimberlite's Macro Menu vX.Y.Z (local build)" that build_window_title() (gui/app/
       update_check.py) actually returns. Likely cause: main.py:250-252 calls both
       app.setApplicationName(APP_NAME) and app.setApplicationDisplayName(APP_NAME); Qt's Windows
       platform plugin automatically appends " - <applicationDisplayName>" to a top-level widget's
       native window title whenever the title does not already exactly equal the display name (a
       documented Qt convenience feature, not something this codebase's own string formatting does),
       which is exactly what build_window_title()'s version/suffix text triggers. Not yet confirmed
       against Qt's actual source/changelog for the exact match condition, and not yet checked
       whether it also affects an official (no-suffix) release title, which happens to already equal
       APP_NAME exactly and so may not show the duplication at all.

Open:  Confirm the Qt applicationDisplayName auto-append theory (or find the real cause) before
       picking a fix; the safest-looking fix is to stop calling setApplicationDisplayName(APP_NAME)
       in gui/app/main.py (or set it to an empty string) since nothing else in the codebase reads
       QApplication::applicationDisplayName(), but confirm there is no other reliance (e.g. Windows
       Alt-Tab/taskbar grouping label) before removing it.
