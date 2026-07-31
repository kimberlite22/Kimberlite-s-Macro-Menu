Title:     Es kommt jetzt config.ini could not be read error 13 permission denied (nur auf dem
           Laptop, auf dem PC läuft alles fine)
Completed: 2026-07-31
Commit:    -

Result: ConfigChangeTracker.changed() (gui/ipc/client.py) used to report a config.ini change to
        main_window.py the instant its mtime differed from the last confirmed value. AHK writes a
        save through many discrete IniWrite/IniDelete calls, and the file's mtime already moves on
        the very first one, so the background status poll could react to that first move and
        re-read config.ini while later writes in the same save were still landing, occasionally
        losing the resulting sharing-violation race even past config_reader.py's own short retry -
        surfacing as "config.ini could not be read" with errno 13. Fixed by requiring the SAME
        mtime to be observed on two consecutive polls before treating it as a real, settled change
        (a config_version bump, only incremented after a save's writes are already complete per
        macro/local_bridge.ahk, is still trusted immediately and unaffected). This scales to any
        write-burst length automatically instead of guessing a fixed retry budget, which is also
        why it should fix the laptop specifically: a slower disk/CPU or heavier antivirus/EDR
        real-time scanning on that machine would stretch AHK's write burst longer than the PC's,
        widening the very race window this removes - the likely reason it reproduced on one machine
        and not the other, though this was not confirmed live per CLAUDE.md's "do not run the app"
        rule.
