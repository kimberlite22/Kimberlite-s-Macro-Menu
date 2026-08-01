Title:     In der macro gui ganz oben engine status remove: "running", "queued", "map", "screen",
           "step", "cycles", step repeats, start repeats, victories, defeats.
Completed: 2026-08-01
Commit:    -

Result: The top "Engine status" box in gui/app/main_window.py now shows only a minimal
        Idle/Running/Paused run-state label; the removed detail line (active/running/queued preset,
        map, screen, step) and counters line (cycles, step repeats, start repeats, victories,
        defeats) are gone from this strip, without touching the underlying LocalStatus/
        local_status.json fields other consumers still read.
