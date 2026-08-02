Title:     hotkeys für bestimme sachen wie: backspace oder delete für "delete selected" usw.
Completed: 2026-08-02
Commit:    -

Result: Wired Delete/Backspace, Ctrl+D, Ctrl+N, F2 (and Ctrl+Up/Ctrl+Down for screens) as
widget-scoped QShortcuts on the steps table and screens list in Edit Preset, matching each
shortcut only to an action that already had a button, and added a confirmation dialog to
_delete_step so keyboard delete always confirms like screen delete already did.
