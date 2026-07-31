Title:     im steps reihenfolge window eine tabelle statt wie jetzt das die werte durch einen | getrennt
sind
Completed: 2026-07-31
Commit:    dc63830

Result: The step order view in Edit Preset is now a QTableWidget with one column per field (Type,
Label, X, Y, End X, End Y, Drag (ms), Wait (s), Flow) instead of a single "|"-joined text line; rows
reorder by dragging the row-number header (avoids QTableWidget's internal-move drag-drop, which swaps
cell contents between rows instead of truly moving a row), and the saved config.ini format is
unchanged.
