Title:     man soll beide windows minimieren können ohne das das andere auch minimiert wird
Completed: 2026-08-01
Commit:    -

Result: All six secondary Qt windows (Edit Preset, Map Advanced Settings, Option Availability,
Advanced Outcomes, Remote Agent Setup, Step Editor) now carry Qt.WindowMinimizeButtonHint
(gui/app/widgets.py's new make_independently_minimizable helper), so they no longer minimize/hide
together with the main window in either direction: previously each was a parented QDialog, which
Windows treats as a native "owned window" that auto-hides whenever its owner minimizes, with no
independent minimize button of its own.
