Title:     solange die application offen ist kann man esc nicht mehr benutzen in anderen programmen.
           Mach das weg
Completed: 2026-07-31
Commit:    -

Result: Escape:: is now guarded by a #HotIf predicate (EscapeHasSomethingToCancel) that only
registers the hotkey while a capture is in progress, the overlay/pin is active, or the macro is
running; otherwise AHK never claims the key and Escape reaches whatever other app has focus.
