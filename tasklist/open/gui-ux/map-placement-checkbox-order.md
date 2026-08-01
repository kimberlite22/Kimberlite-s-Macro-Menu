Title: Map placement tab -> map placement settings, move both checkmarks further down with a small visible space between the field: "number of placements". The order of the checkmarks should be "use custom tower slots for this map" and then the other one
Prio:  3

Goal:  In the Map Placement tab's "Map placement settings" box (gui/app/main_window.py,
       _build_map_tab), both checkboxes move below the "Number of placements" field instead of one
       sitting above it, with a small visible gap between the field and the checkboxes. Checkbox
       order stays "Use custom tower slots for this map" then "Use custom camera actions for this
       map" (already the current order, unaffected by the move).
Open:  -
