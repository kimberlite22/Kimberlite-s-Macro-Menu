Title:     Das macro soll mehrere games supporten die man in general auswählen kann. Sie haben seperate
           conifgs ausser disconnect support und das game window. Aber map placement und alles andere
           ist anders. Es soll auch game specific screens und components geben, bzw screens sind
           komplett game specific, nur manche components sind game specific die werde ich später noch
           angeben
Completed: 2026-08-03
Commit:    -

Result: The macro now supports multiple games selectable from a new "Game" group at the top of the
        General tab (list + New/Rename/Delete + "Switch to Selected"). Each game has its own
        screens/presets/map placement/steps/timing settings; only disconnect support and the
        game-window settings (General tab) stay shared across every game, per the Goal. config.ini
        gains `[Games]` (List/Active) and, per game, `[Game_<name>]` (Timing/Tower Loadout/shared
        Advanced Steps) plus `[Game_<name>_Presets]`/`[Game_<name>_Preset_<name>]` and
        `[Game_<name>_MapProfiles]`/`[Game_<name>_MapProfile_<name>]`, replacing the old flat
        `[Presets]`/`[Preset_<name>]`/`[MapProfiles]`/`[MapProfile_<name>]` sections. A new
        `MigrateToGames()` one-time migration (macro/tower_defense_macro_gui.ahk, modeled on
        `MigrateCoordsToPercent()`) wraps an existing single-game config into one default game
        ("Anime Expedition") the first time it runs, guarded by `[General] GameFormat=v1`; it copies
        everything into the new sections and only writes the completion flag once every copy has
        landed, THEN best-effort deletes the old sections - so an interrupt at any point either loses
        nothing (pre-flag: old data untouched, next launch just re-copies) or leaves harmless old-
        format leftovers (post-flag: migration never re-runs, engine already reads the new sections).
        Every AHK read/write site that used to reference the flat sections or hardcoded `[General]`
        for game-scoped keys now goes through new `GameSection()`/`GamePresetSection()`/
        `GameMapProfileSection()` helpers (keyed off `ActiveGameName`, resolved once at startup by
        `InitGames()`, fixed for the engine process's lifetime). gui/ipc/config_reader.py's
        `read_config()` resolves `games`/`active_game` and merges the shared `[General]` fields with
        the active game's own section into the same `GeneralConfig` shape, so `main_window.py`'s
        widget-population code needed no changes there. gui/ipc/config_writer.py threads a `game`
        keyword parameter through every preset/map-profile mutation function and adds
        `create_game`/`rename_game`/`delete_game`/`set_active_game` (mirroring the preset CRUD
        pattern); `create_game` seeds a default preset/map profile plus explicit non-zero Timing
        defaults (ClickDelayMs=300, PlaceTowerDelayMs=100, MarkerSize=4) so an untouched Save can't
        silently persist a 0 that would otherwise only exist as the engine's own Cfg() fallback.
        Renaming/deleting the currently ACTIVE game is refused outright (not just while running):
        the engine's `ActiveGameName` is fixed for its process lifetime, so doing either to the
        active game out from under a not-yet-restarted engine would point it at sections that no
        longer exist - switch to a different game first. Deliberate scope cut from the original plan:
        switching games persists the change and asks for a manual app restart, rather than attempting
        a live in-place engine-process restart - `MainWindow` does not currently own the engine
        process's lifecycle (that state is local to `main.py`'s own startup function, not stored on
        `self`), so a live restart would need a real refactor beyond this task's safe scope; tracked
        separately if wanted later. Editor windows (Edit Preset, Map Advanced) are now keyed by
        (game, name) instead of bare name, since two games commonly share preset/map-profile names
        and each window can stay open across a later game switch.

        Verification: static reading throughout (CLAUDE.md hard rule: never launch the AHK app or
        gui.exe to test); the full gui/ pytest suite passes (263 passed, including new coverage for
        MigrateToGames-equivalent read behavior via a regenerated fixture, every new config_writer
        game function, the active-game-refusal guards, and the Game group's list/CRUD/reuse
        behavior); a manual `gpt-5.6-terra` read-only Codex review (high effort) over the full diff
        found 5 real issues (migration interruption safety, active-game rename/delete safety, a
        stale-game-at-save-time bug in the Map Advanced window, editor-window identity across a game
        switch, and missing Timing defaults on a new game) - all fixed and covered by new/strengthened
        tests before finishing, per CLAUDE.md's own review-then-fix workflow.

        Workflow note: this task was originally dispatched to a subagent that appeared stuck (~4
        hours, zero commits, no reply to a status check) and was handed off mid-flight to direct
        implementation by the orchestrating session after confirming with the user; the subagent's own
        just-in-time Files:/Steps: plan (based on a real read of the current code) was kept as the
        implementation's starting blueprint even after the handoff, since it was independently
        verified accurate.
