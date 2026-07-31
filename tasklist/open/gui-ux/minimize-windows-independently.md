Title: man soll beide windows minimieren können ohne das das andere auch minimiert wird
Prio:  6

Goal:  Minimizing one of the app's windows does not also minimize the other.
Open:  Which two windows does this refer to? The shipped app normally only shows the single Qt
       main window (the AHK engine runs hidden, per "Python GUI" in CLAUDE.md), so this needs the
       user to say which two windows are actually involved before it can be planned - likely
       candidates: the main window plus a secondary Qt window (Edit Preset, Map Advanced Settings,
       Remote Agent Setup, ...) that currently follows the main window's minimize state, or the main
       window plus the pinned/locked game window during Pin mode ([[pin-rename]]).
