Title:     In presets remove im  widget preset settings die felder, back x back y und fallback screen
           lass nur default map
Completed: 2026-08-02
Commit:    23e39fb

Result: Removed the Back X, Back Y, and Fallback screen rows/widgets from main_window.py's
"Preset settings" group box on the Presets tab, keeping only Default map; the main window's
global Save now passes the selected preset's own back_x/back_y/fallback_screen straight through
instead of reading deleted widgets, so it no longer clobbers those values. The fields remain fully
editable in gui/app/edit_preset_window.py's "Option Select and default map" group box, which
already had its own independent editor and save path for all three (self.back_x, self.back_y,
self.preset_fallback_screen) before this task started.
