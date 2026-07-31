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
          `self.config`, so the poll has nothing left to re-read and cannot clobber the widgets.
       6. Remove those four verbs from protocol.py, client.py, local_bridge.ahk and the AHK writers
          they were the only callers of.

       Stage 2 - the structural operations
       7. Port to Python, against the same document model: CreatePreset (69), RenamePreset (48),
          DeletePreset (37), CreateMapProfile (47), RenameMapProfile (47), DeleteMapProfile (32),
          CreateScreen (27), RenameScreen (40), DeleteScreen (81), MoveScreen (23),
          SET_OPTION_USED_COUNT, SET_OPTION_MAX, EXPORT_PRESET, IMPORT_PRESET.
          RenameScreen and DeleteScreen carry the real logic (they rewrite every step's On True /
          On False reference and renumber the remaining screens); port those two with tests first.
       8. Remove the verbs and the AHK functions behind them.

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
