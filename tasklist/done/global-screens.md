Title:     bei dem neuen screen overhaul die screens sollen global sein alle für jedes preset gleich.
           Nimmm das preset challenges als vorlage für die migration welche screens global sein sollen.
Completed: 2026-07-31
Commit:    -

Result: A screen's entry-detection criteria can now be shared by name across every preset via a new
global registry (`[Screens]`/`[Screen_<name>]` in config.ini), opt-in per preset-screen through a new
"Use global detection" checkbox in the Python screen editor; a preset can still keep fully custom
screens/detections, and a mismatched preset (no name overlap with the seeded registry) is left
completely untouched rather than auto-migrated, per the user's clarification. A one-time migration
(MigrateGlobalScreensSchema, gated on `[General] GlobalScreensSchema=v1`) seeds the registry from the
"Challenges" preset (or the first preset found) and touches nothing else. AHK core
(tower_defense_macro_gui.ahk: ResolveScreenDetection/GlobalScreenNames/ReadGlobalScreenDetection/
WriteGlobalScreenDetection, BuildAllScreensFromIni, RenameScreen's bake-in-before-detach; and
local_bridge.ahk: new SAVE_GLOBAL_SCREEN_DETECTION verb) and the Python GUI (config_reader.py,
protocol.py, edit_preset_window.py, main_window.py) both updated; preset export/import now
bundles/merges referenced global screens (`[GlobalScreen_<name>]` sections), never overwriting an
existing local entry on import. gui pytest suite: 131 passed after updating fixtures/tests for the
new schema.
