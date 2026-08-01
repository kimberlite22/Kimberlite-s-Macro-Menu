Title: hotkeys für bestimme sachen wie: backspace oder delete für "delete selected" usw.
Prio:  6

Goal:  The GUI's list and table widgets react to the usual keyboard shortcuts, so pressing Delete
       or Backspace on a selected step or screen does what "Delete Selected" does, instead of the
       button being the only way.
Open:  Which actions besides delete are in scope ("usw." is open): duplicate (Ctrl+D), add
       (Ctrl+N), move up/down (Ctrl+Up/Down), rename (F2)? Which widgets: the steps table and the
       screens list in Edit Preset only, or also the presets list and the map placement lists in
       the main window? Does a keyboard delete ask for confirmation when the button does not?
       Shortcuts must not collide with the engine's global hotkeys (F7 pin, F8 capture, F9
       pause/resume, F10 start, Escape stop) or steal Backspace from a focused text field.
