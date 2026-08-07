Title:     bei map placements in der tabelle adde ein kleine X button rechts vom capture button der
           das placement removed und das macht automatisch bei dem feld: placements number for this
           map, einen runter. Der button soll nur existieren wenn custom placements for this map
           enabled ist.
Completed: 2026-08-07
Commit:    4a88d00

Result: The placements table gained a sixth column holding a small "X" button per row. Removing a
row shifts the rows below it up, blanks the now-unused last physical row and decrements "Number of
placements" by one; the column is hidden unless "Use custom tower slots for this map" is checked.
The table's fixed-width computation had to move from _build_map_tab into
_update_placements_table_layout so it sums only the currently visible columns, otherwise hiding the
new column would have left dead space to the right of the table.
