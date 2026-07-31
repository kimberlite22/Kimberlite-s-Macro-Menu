Title:     meinst du nicht wir könnten das einfacher direkt machen als so wie es jetzt ist also das
           einfach mal mehr cleanupen mit einmal mehr aufwand aber easier im long run weil das issue
           habe ich schon ewigkeiten und es funktioniert nie gut
Completed: 2026-08-01
Commit:    dcb1ea9 (stage 1), 92ac271 (stage 2), - (stage 3, this PR)

Result: The Python GUI is now the single owner of config.ini, atomically and key-preserving; the AHK
        engine only writes MigrateCoordsToPercent (one-time) plus two small accepted exceptions
        (the per-option daily usage counter during live gameplay, and one Presets.Active= key on a
        remote preset switch). Stage 3 also deleted the ~3400-line hidden native AHK editor GUI
        outright (resolving the task's own open question) and fixed two live bugs it uncovered:
        RemoteBridgeIsEnabled() was reading a dead checkbox instead of config.ini, and DryRun was
        wired to a checkbox that was already unreachable in the shipped app. Verified with a real
        headless engine run (AHK's #Warn diagnostics plus a local_cmd.txt-driven smoke test covering
        START/PAUSE/RESUME/STOP and a full Option-Select gameplay cycle). Step 10 (Cfg() per-run
        caching) remains optional/undone, as originally scoped.
