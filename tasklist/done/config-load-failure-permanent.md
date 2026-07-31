Title:     ok aber selbst wenn ich alte configs lade sind alle zeilen und felder in generell 0
           (nur auf dem Laptop, nicht auf dem PC)
Completed: 2026-07-31
Commit:    -

Result: "Every General field 0" is exactly the GeneralConfig() dataclass default set, i.e. the
        window's "config could not be read" placeholder state, not lost settings. Two real defects
        made that state permanent and dangerous:

        1. It could never recover. _poll_status only called _refresh_config() when
           ConfigChangeTracker reported a change, but until ONE read has succeeded there is
           nothing to compare against. A failed FIRST read (a startup sharing violation while the
           engine is still writing config.ini, or a config.ini that does not exist yet) therefore
           left the window on defaults forever, because the file then sat unchanged and change
           detection never fired again. Now the read is retried on every poll until one succeeds,
           and stops retrying by itself once it does.
        2. Saving in that state destroyed the real config. _save() submitted the placeholder
           zeros through SAVE_GENERAL, overwriting a config.ini that was very likely intact and
           merely unreadable at that moment. Save is now refused while no config has ever loaded,
           with an explicit message. The already-loaded-once case stays allowed, since there the
           widgets hold the last known-good values.

        The notice bar now also states that the fields are placeholders, that saving is blocked,
        and that the read is being retried, instead of just "Defaults are shown".

        This is the same laptop-only failure as [[config-read-race-on-save]]: that task removed the
        mid-save-burst race in the background poll, but the STARTUP read is a separate path it did
        not cover, and nothing made a failure there recoverable. Not reproduced live (the reporting
        machine is a different one, and CLAUDE.md forbids running the app here); the placeholder
        signature and the two code paths were confirmed by reading and by tests that fail without
        each fix.
