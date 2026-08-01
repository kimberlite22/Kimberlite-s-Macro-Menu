Title:     ok but increase the space between the line and the box with presets a litte bit
Completed: 2026-08-01
Commit:    -

Result: Added an 8px `addSpacing` gap between the preset list/buttons row and the "Runs on Start" / "Set as Active" row inside the Presets group box on the Preset Settings tab (gui/app/main_window.py, _build_preset_tab), so the two rows no longer sit flush against each other; the group box's outer border still encloses both rows unchanged.
