Title:     Bei koordinaten x und y adde einen button wie bei ocr show region das wenn man den drückt die
           location auf dem bildschirm briefly zeigt
Completed: 2026-08-02
Commit:    -

Result: Added a "Show" point-preview button (a brief crosshair flash on screen, converted from
        percent-of-opening via AHK's AbsXY, same mechanism as the OCR "Show Region" button but for a
        single point) next to every in-scope X/Y coordinate field: Map Placement's per-slot
        placements_table rows (main_window.py), Edit Preset's Back X/Y (edit_preset_window.py), and
        in the Step Editor (step_edit_window.py) both step_x/step_y and step_end_x/step_end_y, plus
        each of the three Challenge options' X/Y in options_box.
