Title: Complete Logic overhaul. Ein screen hat jetzt zum default eine "screen detection ganz am
anfang", etwas durch das man den current screen erkennt. Dann komme die restlichen steps die
reihenfolge. Am ende des screens kommt wird automatisch wieder die global screen detection
ausgeführt und je nach dem was rauskommt wird auf den corresponding screen geswitched. Bei einem
konflikt also wenn mehere detections gleichzeitig true liefern kann man am ende eines screens ein
default auswählen der dann unter allen screens die gleichzeitg true liefern ausgewählt wird.
Prio:  6

Goal:  A screen is self-identifying: it starts with its own entry detection, then runs its steps,
       then the global screen detection decides which screen comes next. Ties are resolved by a
       per-screen configured default instead of by step order.
Files: macro/tower_defense_macro_gui.ahk (RunSteps detection cases, MainLoop, screen/step schema
       in config.ini, migration in the style of MigrateCoordsToPercent),
       gui/app/edit_preset_window.py (screen/step editor), gui/ipc/config_reader.py
Steps: 1. Design the config schema addition: per screen an entry detection plus a "default screen
          on conflict" field, and a one-time migration that gives existing screens a sane default.
       2. Extract a reusable "detect current screen" routine out of the existing RunSteps cases,
          evaluating every screen entry detection and returning the full set of matches.
       3. Run it at the end of each screen, resolve multiple matches via the configured default,
          switch. Keep the pause / emergency stop / StopRequested checks intact on that path.
       4. Mirror the new fields in the Python GUI editor and config_reader (plus their tests).
       5. Add a bounded retry so an unrecognized screen cannot spin forever.
Open:  What happens when nothing matches (stay and retry, abort, fall back to a start screen)?
       Is the "global screen detection" simply the union of all entry detections, or a separately
       configured one? What if the configured default is not among the matches?
