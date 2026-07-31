Title:     uhh und nach ein bisschen testen kommt gerade bei mir: unhandled error :1934 glaube ich
           ich bin mir aber nicht sicher die message war schnell weg
Completed: 2026-07-31
Commit:    -

Result: LoadGeneralSlots(), LoadMapProfile() and LoadPreset() in macro/tower_defense_macro_gui.ahk
        now route numPlaceDdl/GeneralSlotDdls[i]/mapNumPlaceDdl/row.CustomSlotDdl/opt.PrioDdl
        through the existing SetDdlTextSafe() helper instead of a bare `.Text :=` assignment, so a
        stale or out-of-range config value (Option Priority, General slot, a placement count) falls
        back to a safe default instead of throwing "Unhandled error: Invalid value." at every
        engine launch.
