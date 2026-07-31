Title: In der macro gui ganz oben engine status remove: "running", "queued", "map", "screen",
       "step", "cycles", step repeats, start repeats, victories, defeats.
Prio:  8

Goal:  The engine status strip at the top of the macro GUI (gui/app/main_window.py) no longer shows
       the listed fields (running, queued, map, screen, step, cycles, step repeats, start repeats,
       victories, defeats).
Open:  Are all of these removed outright, or moved elsewhere (e.g. into the stats box redesign from
       [[detailed-stats]])? What should the status strip show instead, if anything?
