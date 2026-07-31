Title:     die general page ist gerade kind of broken, ich habe alte config backups geladen aber
           timing tower loudout sind alle auf 0 oder none
Completed: 2026-07-31
Commit:    -

Result: The Tower Loadout dropdowns (General tab) were populated from _all_option_names(), i.e. the
        preset's challenge option names ("Option 1/2/3"), a completely different concept from what
        a tower slot actually is. The engine builds the very same fields as DropDownLists over
        ["1".."6"] (the game's hotbar positions, see GeneralSlotDdls in
        macro/tower_defense_macro_gui.ahk) and reads them back with SetDdlTextSafe(..., "1"). The
        GUI therefore offered choices the engine cannot use, and the real saved value was not among
        them, so the widget looked unset. Introduced by fecefc7, which made these pickers
        select-only; while they were free text the wrong item list was invisible. Fixed by
        populating them from a new TOWER_SLOT_CHOICES constant mirroring the engine, falling back
        to "1" for a value outside that list exactly as SetDdlTextSafe does.

        No data was lost: the user's config.ini and every config_backups entry back to 2026-07-29
        hold identical values (Slot1=5, Slot2=5, Slot3=5, Slot4=4, rest 1; ClickDelayMs=300,
        PlaceTowerDelayMs=100). The "timing all 0" part of the report was not a bug at all -
        RoundWaitSeconds=0 and MaxRounds=0 are the user's own long-standing settings (no extra
        cycle wait, no cycle limit), and the reader/window were verified to display ClickDelayMs
        and PlaceTowerDelayMs correctly from that exact file.

        gui/tests/fixtures/sample_config.ini stored Slot1..Slot10 as names (Alpha, Beta, ...),
        encoding the same wrong model, which is why no test caught this; it now holds realistic
        hotbar numbers.
