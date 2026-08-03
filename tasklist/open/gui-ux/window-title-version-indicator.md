Title: display current version and wether or not this is a local built .exe in the window bar
       above the application window
Prio:  2

Goal:  The main window's title bar (currently just APP_NAME, set via setWindowTitle in
       gui/app/main_window.py) also shows the running app's version (read the same way
       gui/app/update_check.py's read_current_version already does) and whether this is a locally
       built exe versus an official release build (gui/app/launcher_paths.py's is_frozen() plus
       whatever already distinguishes a release build from a local one).
Open:  What should count as "local built" versus "official release" - is there already a reliable
       signal to distinguish the two (e.g. a release-only marker file, a different VERSION
       provenance), or does one need to be added?
