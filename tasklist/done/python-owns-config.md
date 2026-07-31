Title: meinst du nicht wir könnten das einfacher direkt machen als so wie es jetzt ist also das
       einfach mal mehr cleanupen mit einmal mehr aufwand aber easier im long run weil das issue
       habe ich schon ewigkeiten und es funktioniert nie gut
Prio:  1

Goal:  The Python GUI is the single owner of config.ini: it writes the file itself, atomically and
       key-preserving, and the AHK engine only reads it. Saving stops being a bridge round trip, so
       the sharing violations, ack timeouts, busy rejections and half-saved configs that come from
       two processes writing one INI file cannot happen any more.

Why:   Four defects feed each other today.
       1. Two owners. Python re-reads config.ini from disk every 250ms (main_window.py `_poll_status`)
          while the engine writes it. Every save is a race.
       2. Per-key writes. `IniWrite` rewrites the WHOLE file per key, and there are 197 call sites.
          One Save click fires SAVE_GENERAL (34 writes) plus SAVE_MAP_PROFILE plus SAVE_PRESET, so
          hundreds of full rewrites of a ~98KB file back to back, each holding an exclusive lock.
          Measured on a fast desktop against the real 97,898-byte config: 34 writes 16ms, 600 writes
          187ms. On a laptop with a slower disk and live antivirus scanning that is seconds.
       3. Per-key reads. `Cfg()` is a bare `IniRead` with no cache (tower_defense_macro_gui.ahk:146)
          across 199 call sites, so the engine also re-reads the whole file constantly.
       4. Save is three separate bridge commands, each with its own token, ack and 5s timeout. A
          partial failure leaves config.ini half written and only reports a joined status-bar string.
       This is also how a config gets silently zeroed: the failure modes all end in the GUI holding
       placeholder values that a later save writes back. See tasklist/done/config-load-failure-permanent.md
       for the 0.4.15 patch, which only narrowed the window instead of removing it.

Files: gui/ipc/config_writer.py   NEW: key-preserving INI document + atomic write + backup rotation
       gui/ipc/config_reader.py   reuse its parsing; keep read_config as the typed view
       gui/ipc/client.py          drop the write verbs as they are ported
       gui/ipc/protocol.py        drop the corresponding VERB_/payload builders
       gui/app/main_window.py     `_save`, `_poll_status`, `_refresh_config` write locally
       gui/app/edit_preset_window.py, map_advanced_window.py, option_availability_window.py,
                                  advanced_outcomes_window.py: same, where they send write verbs
       macro/local_bridge.ahk     remove the ported handlers and their JSON field helpers
       macro/tower_defense_macro_gui.ahk
                                  remove the now-dead writers (SaveGeneralFromData, SavePresetToIni,
                                  SaveMapProfileToIni, CreatePreset/RenamePreset/DeletePreset,
                                  CreateMapProfile/RenameMapProfile/DeleteMapProfile,
                                  CreateScreen/RenameScreen/DeleteScreen/MoveScreen, ~515 lines)
       gui/tests/                 one module per new writer concern

Steps: Staged so the app is fully working after each stage.

       Stage 1 - the Save button (removes the chronic pain)
       1. gui/ipc/config_writer.py: an ordered INI document that round-trips a file it did not
          write. It must preserve unknown keys (RegionX1, StartX, ScreenWidth, CenterCamera,
          AdvStepsMigrated, CoordFormat, ScreenDetectionSchema, ...), section and key order, and the
          UTF-16LE BOM with CRLF that AHK IniRead expects. Apply changes as a key/value overlay, never
          serialize from the typed model alone, or every unmodelled key is silently deleted.
       2. Atomic write: .tmp in the same directory then os.replace, mirroring the bridge helpers.
          A reader can then only ever see the old or the new file, never a truncated one.
       3. Port BackupConfig() (tower_defense_macro_gui.ahk:4645) including its rotation policy.
       4. Validate before writing: reject a save that would store HoleW/HoleH = 0, the exact state
          that silently breaks every coordinate (AbsXY falls back to raw pixels).
       5. `_save` writes the file directly instead of sending SAVE_GENERAL / SAVE_PRESET /
          SAVE_MAP_PROFILE / SAVE_ADV_MAP_STEPS, and feeds the written document straight back into
          `self.config`, so the poll has nothing left to re-read and cannot clobber the widgets. DONE
          for main_window.py (general/preset/map_profile), edit_preset_window.py (preset) and
          map_advanced_window.py (map_profile + adv_steps, now one combined save_config() call
          instead of two separate bridge round trips).
       6. Remove those four verbs from protocol.py, client.py, local_bridge.ahk and the AHK writers
          they were the only callers of. DONE: the VERB_SAVE_* constants are gone from protocol.py,
          the local_bridge.ahk SAVE_* case blocks and their local-bridge-only helpers
          (LocalBridgeSavePreset, LocalBridgeSaveMapProfile, LocalBridgeSaveAdvMapSteps,
          LocalBridgeGeneralFields, LocalBridgeSyncGeneralControls, LocalBridgeReplacePresetScreens,
          LocalBridgeScreenFromJson/StepFromJson/OptionFromJson) are removed. The underlying AHK
          writers (SaveGeneralFromData, SavePresetToIni, SaveMapProfileToIni, SaveMapAdvStepsArr,
          WriteScreenSteps) are kept: the hidden native GUI and the still-bridge-based structural
          operations (NEW_/RENAME_/DELETE_* etc., Stage 2) still call them directly.

       Stage 2 - the structural operations. DONE, with one scope correction found along the way:
       7. Port to Python, against the same document model: CreatePreset, RenamePreset, DeletePreset,
          CreateMapProfile, RenameMapProfile, DeleteMapProfile, SET_OPTION_USED_COUNT,
          SET_OPTION_MAX, EXPORT_PRESET, IMPORT_PRESET. DONE in gui/ipc/config_writer.py
          (create_preset/rename_preset/delete_preset/export_preset/import_preset/
          create_map_profile/rename_map_profile/delete_map_profile/set_option_used_count/
          set_option_max, all raising the new MutationError on a rejected mutation) plus 18 new
          tests in gui/tests/test_config_writer.py. gui/app/main_window.py now calls these through
          new ipc/client.py methods instead of sending NEW_/RENAME_/DELETE_*/EXPORT_PRESET/
          IMPORT_PRESET/SET_OPTION_* over the bridge; _run_local_mutation() is the local counterpart
          of the old verb-based _run_mutation() (which stays, SET_ACTIVE_PRESET is deliberately not
          part of this list - see below).

          CreateScreen/RenameScreen/DeleteScreen/MoveScreen were NOT ported: turns out the Python
          GUI never called their NEW_SCREEN/RENAME_SCREEN/DELETE_SCREEN/MOVE_SCREEN bridge verbs in
          the first place - gui/app/edit_preset_window.py already reimplements screen add/rename/
          delete/move entirely client-side (`_new_screen`/`_rename_screen`/`_delete_screen`/
          `_replace_targets`), including the On True/On False/fallback/outcome reference rewrite
          RenameScreen/DeleteScreen carry, and persists the result through the whole-preset save
          payload Stage 1 already ported. Confirmed by grep: no `VERB_NEW_SCREEN` et al. call site
          existed anywhere under gui/app/. So those four verbs were already dead weight, not a
          porting gap - removed as dead code instead (see step 8).
       8. Remove the verbs and the AHK functions behind them. DONE for the verbs: every one of the
          ten ported verbs above, PLUS the always-dead NEW_SCREEN/RENAME_SCREEN/DELETE_SCREEN/
          MOVE_SCREEN, are gone from local_bridge.ahk (their case blocks, LocalBridgeKnownVerb's
          list, and the local-bridge-only helpers that only existed to serve them:
          LocalBridgeSetOptionUsedCount/SetOptionMax/OptionIndex/ExportPreset/ImportPreset/
          MapProfileExists/RequiredScalarField) and from gui/ipc/protocol.py (VERB_* constants and
          payload builders). NOT done for "the AHK functions behind them"
          (CreatePreset/RenamePreset/DeletePreset/CreateMapProfile/RenameMapProfile/
          DeleteMapProfile/CreateScreen/RenameScreen/DeleteScreen/MoveScreen themselves, in
          tower_defense_macro_gui.ahk): every one of those is still the only implementation the
          hidden native AHK GUI's own New/Rename/Delete/Move buttons call
          (NewPresetClick/RenamePresetClick/... etc.), and whether that native GUI's own controls
          survive at all is exactly the open question below - deleting the functions now would
          break it before that question is answered.

       Stage 3 - leave the engine read-only
       9. The only engine-side writer left is MigrateCoordsToPercent (one-time, before the GUI is up).
          Keep it, and keep the config version counter so a migration still notifies the GUI.
      10. Optional, separate: give `Cfg()` a per-run cache so the engine stops re-reading a 98KB file
          199 times. Not required for correctness, only for speed.

Open:  - Storage format stays INI for now. Moving to JSON would remove the percent migration, the
         AdvStep<N><Field> numbering and the flattened "Name=Screen|..." outcome strings, but the cost
         sits on the engine's READ side (199 Cfg() call sites), so it is its own task, not part of this.
       - Whether the hidden native AHK GUI's own Save button and its Build*SaveData helpers should be
         deleted outright in Stage 3 or kept as a dev-only escape hatch.
