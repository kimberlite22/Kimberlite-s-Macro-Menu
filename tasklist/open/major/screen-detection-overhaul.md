Title: Complete Logic overhaul. Ein screen hat jetzt zum default eine "screen detection ganz am
anfang", etwas durch das man den current screen erkennt. Dann komme die restlichen steps die
reihenfolge. Am ende des screens kommt wird automatisch wieder die global screen detection
ausgeführt und je nach dem was rauskommt wird auf den corresponding screen geswitched. Bei einem
konflikt also wenn mehere detections gleichzeitig true liefern kann man am ende eines screens ein
default auswählen der dann unter allen screens die gleichzeitg true liefern ausgewählt wird.
Prio:  1

Goal:  A screen is self-identifying: it starts with its own entry detection, then runs its steps,
       then the global screen detection decides which screen comes next. Ties are resolved by a
       per-screen configured default instead of by step order.
Files: macro/tower_defense_macro_gui.ahk (RunSteps detection cases, MainLoop, screen/step schema
       in config.ini, migration in the style of MigrateCoordsToPercent),
       gui/app/edit_preset_window.py (screen/step editor), gui/ipc/config_reader.py
Steps: 1. Config schema: add per screen (new `Screen<i>Detection*` keys in `Preset_<name>`, next to
          the existing `Screen<i>Name`/`Screen<i>StepCount`): `DetectionType` (one of the existing
          Logic step types - Detect Map / Round End Detection / Ingame Detection / Custom Detection -
          or empty for "no entry detection configured"), `DetectionX/Y/EndX/EndY` (region, same
          percent-of-opening convention as step regions), `DetectionText` (reuse whatever field name
          the existing Custom Detection step case already uses for its match text), and
          `DefaultScreen` (name of the screen to fall back to when THIS screen's run ends: used both
          on a zero-match result and, on a multi-match conflict, when this default is itself among
          the matches).
       2. One-time migration `MigrateScreenDetectionSchema()`, modeled on `MigrateCoordsToPercent`
          (backup config.ini first, gate on a stamped `[General]` key e.g. `ScreenDetectionSchema=v2`
          so it runs once): for every existing screen missing `DetectionType`, set it to empty and
          set `DefaultScreen` to the name of the next screen in the existing list order (wrapping to
          the start screen found by `FindStartScreenIndex`). This exactly reproduces today's
          `screenIdx + 1` fallthrough in `MainLoop`, so migrated presets behave identically until a
          user opts into configuring a real entry detection on a screen.
       3. Extract a reusable `DetectCurrentScreen(presetScreens)` routine, generalizing the matching
          logic already embedded in `RunSteps`'s Logic step cases (`Detect Map` / `Round End
          Detection` / `Ingame Detection` / `Custom Detection`, currently ~6906-6961) so it runs
          against a screen's `Detection*` fields instead of a step's fields. Skip screens with an
          empty `DetectionType` (never match). Evaluate every screen in preset list order and return
          the FULL ordered set of matches, not just the first (this set is the "global screen
          detection", i.e. the union of all screens' entry detections run in order). Check
          `Running`/`Paused` between each screen's scan, same as `RunSteps`'s existing per-step
          checks (~6710-6716), and abort early (returning a distinct "aborted" result) if a stop
          lands mid-scan, so `MainLoop` can exit its `while Running` loop the same way it does today
          instead of acting on a stale/partial match set.
       4. Hook the resolution into `MainLoop` at the exact spot that today falls through to
          `screenIdx + 1` (~6519-6521): call `DetectCurrentScreen`, then resolve:
            - aborted (stop/pause interrupted) -> do not switch, let the existing `while Running`
              exit handle it.
            - exactly one match -> switch to it.
            - zero matches -> log a warning naming the screen that just ran and the default it is
              falling back to, then switch to that screen's configured `DefaultScreen`.
            - multiple matches (conflict) -> if the screen's `DefaultScreen` is itself among the
              matches, switch to it; otherwise switch to the first matched screen in preset order,
              NOT the default (a spurious conflict, e.g. a disconnect popup overlapping the real
              screen, must not be papered over by defaulting away from what was actually observed).
       5. Bounded retry: track a consecutive-zero-match counter across `MainLoop` iterations (reset
          to 0 whenever a detection pass produces at least one real positive match, even a conflict;
          incremented only on a pure zero-match fallback). If it exceeds a small constant (5), that
          means even the configured `DefaultScreen` chain never gets positively detected, i.e. a
          misconfigured or genuinely unrecognizable state - log a clear error and stop the macro the
          same way an emergency stop does, rather than looping silently forever.
       6. Mirror the new per-screen fields in `gui/ipc/protocol.py` (`ScreenPayload`),
          `gui/ipc/config_reader.py` (`ScreenConfig` + a `_read_screen_detection`-style parser next to
          `_read_preset`/`_read_step`, reusing the existing percent-coordinate parsing steps already
          use for X/Y/EndX/EndY), and `gui/app/edit_preset_window.py` (the "Screens" box currently has
          only a reorderable name list with no per-screen settings; add a settings panel shown for the
          selected screen: detection type dropdown, region capture reusing the existing
          capture.py/crosshair flow used for step regions, a text field, and a "Default screen on
          conflict" dropdown populated from the other screen names in the same preset). Add/extend
          tests under `gui/tests/` for all three.
       7. The legacy AHK-side `Gui` screen/step editor (never shown in the shipped app, see CLAUDE.md
          "Python GUI: DONE") is out of scope: only the engine (schema/migration/MainLoop) and the
          Python editor need the new fields.
Open:  Resolved 2026-07-31 (see chat): (1) zero matches -> warn, then fall back to the screen's
       configured `DefaultScreen` (also the destination the bounded retry ultimately gives up on).
       (2) "global screen detection" = every screen's entry detection evaluated in preset list order,
       unconditionally (no separate config). (3) if the configured default is not among the matches,
       switch to whichever screen actually matched, never silently prefer the default, since errors
       (e.g. a disconnect mid-map) must still be reflected rather than masked.
