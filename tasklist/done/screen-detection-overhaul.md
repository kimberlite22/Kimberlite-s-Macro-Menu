Title: Complete Logic overhaul. Ein screen hat jetzt zum default eine "screen detection ganz am
anfang", etwas durch das man den current screen erkennt. Dann komme die restlichen steps die
reihenfolge. Am ende des screens kommt wird automatisch wieder die global screen detection
ausgeführt und je nach dem was rauskommt wird auf den corresponding screen geswitched. Bei einem
konflikt also wenn mehere detections gleichzeitig true liefern kann man am ende eines screens ein
default auswählen der dann unter allen screens die gleichzeitg true liefern ausgewählt wird.
Completed: 2026-07-31
Commit:    9af9a4f

Result: every screen now carries its own entry detection (Detect Map / Round End Detection / Ingame
Detection / Custom Detection) plus a default-screen-on-conflict field. MainLoop evaluates every
screen's entry detection whenever no step explicitly jumps, and resolves a single match directly,
a zero-match result by warning and falling back to the configured default, and a multi-match
conflict by preferring the default only when it was itself observed, otherwise the first real
match (so a spurious conflict is never papered over). A bounded 5-attempt zero-match counter stops
the macro rather than looping forever. A one-time migration keeps existing presets behaviorally
unchanged until a screen opts in, and the Python GUI editor/protocol/config reader mirror the new
fields end to end, including the local_bridge.ahk SAVE_PRESET round-trip and the native
Delete/Move/Rename Screen paths (which previously would have dropped or misplaced the new fields).
