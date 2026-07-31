Title:     wenn man die default map auswählt bei preset settings muss man den namen typen. Mach das ein
dropdown menü kommt wo man auswählen kann. Fixe auch andere vorkommen davon.
aber ich habe gemerkt das das mit jedem dropdown menü so ist fixe das für alle
Completed: 2026-07-31
Commit:    -

Result: preset_default_map, preset_fallback_screen, and the ten general_slot_N combos on the
Preset Settings / General tabs are now select-only dropdowns instead of editable free-text combos
(general_game_process stays editable, intentionally, since a typed value is meaningful there);
general_slot_N combos, which previously had no items at all, are now populated from the option/tower
names used across all presets.
