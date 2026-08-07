Title: update in map placements die advanced settings so das sie uptodate mit dem aktuellen step
       editor sind
Prio:  1

Goal:  The step editor inside "Map Advanced Settings..." (reached from the Map Placement tab) is
       back in sync with the preset Step Editor it was copied from. The concrete gap is the "Show"
       point-preview button: commit 316a23a wired it into the Step Editor's start/end coordinates,
       Map Placement's per-slot table and Edit Preset's Back X/Y, but skipped this window, so a
       map's Drag start/end coordinates are the only coordinates left in the app that cannot be
       previewed on screen.

Files: gui/app/map_advanced_window.py (the "Step Editor" QGroupBox built in _build_ui, plus the
       capture handlers below it), gui/tests/test_map_advanced_window.py. The point-preview wire
       protocol already exists on both sides and needs no change: VERB_SHOW_POINT_PREVIEW /
       show_point_preview_payload in gui/ipc/protocol.py, handled by macro/local_bridge.ahk and
       ShowPointPreview() in macro/tower_defense_macro_gui.ahk.

Steps: 1. Compare gui/app/map_advanced_window.py's Step Editor against
          gui/app/step_edit_window.py field by field and list what is genuinely missing rather
          than merely different. Differences that are deliberate stay: this window edits only
          Drag / Zoom Out camera actions, so Name, Wait After, Once per cycle, the on-true /
          on-false targets, the fallback rows, Advanced Detection and the Challenge options box
          have no meaning here, and its two separate "Capture start" / "Capture end" buttons are
          better for a drag than the Step Editor's single "Set Position".
       2. Add a "Show" button next to the start coordinates and one next to the end coordinates,
          matching step_edit_window.py's show_position_button / show_end_position_button: same
          "Show" text, same object-name convention (map_advanced_show_start_button /
          map_advanced_show_end_button), sending VERB_SHOW_POINT_PREVIEW with
          show_point_preview_payload(x, y) read live from the spin boxes.
       3. Report the outcome through this window's own status label via _message(), in the same
          "SHOW_POINT_PREVIEW: <result> (<message>)" shape step_edit_window._show_point_preview
          uses, and catch IpcTimeoutError / IpcBusyError separately the way it does, so a busy or
          missing engine cannot raise out of a button handler.
       4. Keep the existing visibility rule: everything except Type and the first coordinate is
          hidden for a "Zoom Out" step (its X is a wheel-tick count, not a coordinate), so both
          new buttons follow the same _set_visible keys the coordinate rows already use.
       5. Extend gui/tests/test_map_advanced_window.py: the buttons exist, clicking each sends
          VERB_SHOW_POINT_PREVIEW with the values currently in the spin boxes, both are hidden for
          a Zoom Out step, and a raised IpcTimeoutError / IpcBusyError reaches the status label
          instead of propagating.

Open:  -
