Title: bei map placements in der tabelle adde ein kleine X button rechts vom capture button der das
       placement removed und das macht automatisch bei dem feld: placements number for this map,
       einen runter. Der button soll nur existieren wenn custom placements for this map enabled
       ist.
Prio:  1

Goal:  Each row of the Map Placement tab's placements table has a small "X" button at the end of
       the row that removes that placement: the rows below it move up by one and the "Number of
       placements" field drops by one, so the table's visible length follows automatically. The
       button is only present while "Use custom tower slots for this map" is checked, since that
       checkbox is what makes the per-map placement count effective in the first place.

Files: gui/app/main_window.py: the placements table built in _build_map_tab (the QTableWidget, its
       column widths and the setFixedWidth call), _update_placements_table_layout, and the
       _capture_placement / _show_placement / _placement_cell handlers next to which the new
       remove handler goes. Tests in gui/tests/test_main_window.py.

Steps: 1. Grow the table from 5 to 6 columns and give the new last one a narrow width and a
          per-row QPushButton("X"), objectName placement_remove_button_<row>, built in the same
          loop that already builds the Capture and Show buttons. Last column, not between Capture
          and Show: it is still right of Capture as asked, and a destructive button does not
          belong next to the button the user clicks most.
       2. Removing row N shifts rows N+1..9 up by one and blanks the now-unused last row, so the
          list closes up instead of leaving a hole. Only columns 0-2 (Custom slot, X, Y) hold
          data; the button cell widgets belong to the row, not the placement, and must not move.
       3. Then decrement map_num_placements by one, floored at 0. Its valueChanged is already
          connected to _update_placements_table_layout, so the table's visible length follows on
          its own; do not also hand-roll the re-layout.
       4. Show the column only while map_custom_towers is checked, driven from
          _update_placements_table_layout (already called on map_custom_towers.toggled,
          map_num_placements.valueChanged and profile load) via setColumnHidden. The table has a
          FIXED width computed from the column widths in _build_map_tab, so that computation has
          to move into the same method and sum only the visible columns, otherwise hiding the
          column leaves dead space.
       5. Nothing here saves: like the existing Capture button, removal edits the table in place
          and the tab's own Save button writes it. _map_profile_payload already reads all ten
          physical rows, so a shifted-up table serializes correctly with no change there.
       6. Tests: removing a middle row shifts the ones below it up and blanks the last row;
          map_num_placements drops by one and the visible row count follows; the column is hidden
          while map_custom_towers is unchecked and visible when checked; removing at count 0 or on
          the last row cannot push the count below 0.

Open:  -
