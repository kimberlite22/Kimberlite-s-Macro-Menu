Title: In live stats when the default map is the active map dont just display none display the
       default map name the same way the others are
Prio:  2

Goal:  The Live Stats tab's "Current Map" shows the map the macro is actually running on, including
       when that is the configured Default Map, instead of "(none)". Today it reports "(none)"
       precisely in the case where the macro is happily using a map: macro/local_bridge.ahk:603
       publishes currentMap from LastDetectedMap, which stays empty when detection did not run or
       matched nothing, while everything downstream in the engine goes through ResolveMapName(),
       which falls back to the per-preset Default Map. So the status field and the engine disagree
       about which map is in use, and the GUI faithfully renders the wrong one
       (gui/app/live_stats_tab.py:211 and :240, `status.current_map or "(none)"`).

       The fix belongs on the engine side, in what the status reports, not in the GUI's fallback
       text: publishing the resolved map means the Copy-able stats line and the tile agree with the
       log line "No map detected - using Default Map: <name>." that the same run already prints.
       "(none)" then means what it says, no map detected AND no Default Map configured.

Open:  - Whether the tile should distinguish a DETECTED map from a fallback to the Default Map (for
         example "Forest" against "Forest (default)"), or just show the name plainly as the user's
         wording asks for ("the same way the others are"). Plain name is the literal reading;
         confirm before adding a suffix, since a suffix is exactly the sort of extra text the user
         did not ask for.
       - ResolveMapName() is per-preset and deliberately uses the ACTUALLY running preset, not the
         one selected in the list (see its comment near macro/tower_defense_macro_gui.ahk:4682).
         The status writer runs on its own tick, so check which preset it is resolving against
         before wiring it up, or a mid-run preset switch would report the wrong default.
