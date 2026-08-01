Title:     Map placement tab -> map placement settings, move both checkmarks further down with a small visible space between the field: "number of placements". The order of the checkmarks should be "use custom tower slots for this map" and then the other one
Completed: 2026-08-01
Commit:    -

Result: Both checkboxes in the Map Placement tab's "Map placement settings" box now sit below the
"Number of placements" field, separated from it by a small QSpacerItem-driven gap, with their
relative order unchanged (custom tower slots, then custom camera actions).
