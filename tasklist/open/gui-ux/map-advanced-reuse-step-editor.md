Title: in advanced settings the old gui is still there. The gui should be like the normal preset
       edit ui
Prio:  1

Goal:  Follow-up from map-advanced-sync-step-editor: that task read "up to date with the current
       step editor" as the one feature the window had missed (the Show point-preview buttons) and
       left its layout alone, but what was actually wanted is that the Map Advanced Settings window
       LOOKS AND WORKS like the normal preset edit UI. It gets the preset editor's step table plus
       Add / Edit / Delete / Duplicate buttons, and editing an action opens the SAME StepEditWindow
       the preset editor uses, restricted to Drag and Zoom Out. Chosen over a lookalike second
       editor so the two can never drift apart again, which is the root cause this follow-up exists
       at all.

Files: gui/app/step_edit_window.py (a map-action mode plus an end-position capture button),
       gui/app/map_advanced_window.py (the whole step list and inline editor), and the tests
       gui/tests/test_step_edit_window.py, gui/tests/test_map_advanced_window.py. The pattern to
       mirror is gui/app/edit_preset_window.py: STEP_TABLE_COLUMNS, _render_steps,
       _step_row_texts, _sync_steps_order, _step_row_moved, _open_step_editor,
       _save_step_from_editor, _delete_step, _duplicate_step.

Steps: 1. StepEditWindow gains a keyword-only map_action_mode flag. In that mode its type combo
          holds only Drag and Zoom Out, and _update_field_visibility force-hides every field
          AdvancedStep has no place to store: Name, Wait After, Once per cycle, Then Go To,
          On False, the three fallback rows, Advanced Detection, Configure Outcomes, Test OCR and
          the Challenge options box. Window title "Map Action Editor".
       2. Add open_for_map_action(step: AdvancedStep | None) that loads an AdvancedStep into the
          same widgets. The saved signal keeps emitting a StepConfig: AdvancedStep's six fields are
          exactly StepConfig's first six, so the caller converts and no signal type changes, which
          keeps the preset editor's own wiring untouched.
       3. Add a "Set End Position" capture button to StepEditWindow, visible only for a Drag step.
          Without it, moving the map window onto the shared editor would LOSE its "Capture end"
          button, since the preset editor's single "Set Position" only ever fills X/Y for a Drag.
          This also fixes the preset editor, where a Drag step's End X/End Y could until now only
          be typed in by hand.
       4. Rebuild MapAdvancedWindow's list as a QTableWidget with columns Type, X, Y, End X, End Y,
          Drag, reordered by dragging the row-number header (sectionMoved), NOT by
          InternalMove drag-drop: see the comment in edit_preset_window.py, QTableWidget's internal
          move swaps cell contents between rows and would scramble fields across actions. Row 0 of
          each row carries the AdvancedStep in Qt.ItemDataRole.UserRole, cells are non-editable, and
          a Zoom Out row shows "<n> ticks" in X with the other coordinate cells blank, matching
          _step_row_texts.
       5. Replace Add Step / Update Selected / Remove Selected / Move Up / Move Down with the
          preset editor's Add Step / Edit Step... / Delete Selected / Duplicate, the same
          Delete/Backspace/Ctrl+D/Ctrl+N/F2 shortcuts and the same delete confirmation. Move Up /
          Move Down go away: header dragging replaces them, exactly as in the preset editor.
       6. Track the step being edited by object identity, not row number, the way
          _open_step_editor / _save_step_from_editor do: the table stays interactive while the
          non-modal editor is open, so a row number can silently repoint at a different action.
       7. Delete the whole inline "Step Editor" group box, including the Show buttons added by
          map-advanced-sync-step-editor. They are not lost: the shared StepEditWindow has had them
          since 316a23a, which is the entire point of reusing it.
       8. Keep untouched: the custom_camera checkbox and its _custom_camera_toggled reset, the
          _steps_by_section / _effective_section model, _current_profile_snapshot,
          _build_profile_payload and _save. This task changes how actions are presented and edited,
          never how they are stored or written.
       9. Tests: map_action_mode hides the non-applicable fields and offers only the two types;
          open_for_map_action round-trips an AdvancedStep; the end-capture button fills End X/End Y
          and is Drag-only; the map table renders a Zoom Out row with ticks and blanks; add, edit,
          duplicate and delete change the in-memory list; header reordering rewrites the order
          without scrambling fields; and an edit committed after the underlying row moved still
          lands on the right action.

Open:  -
