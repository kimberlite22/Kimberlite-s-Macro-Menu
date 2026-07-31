Title: im steps reihenfolge window eine tabelle statt wie jetzt das die werte durch einen | getrennt
sind
Prio:  5

Goal:  The step order view is a real table with one column per field instead of one text line with
       | separators.
Files: gui/app/edit_preset_window.py (step list), gui/app/widgets.py, gui/tests/
Steps: 1. Replace the list widget with a table/tree widget, one column per step field.
       2. Keep drag-to-reorder working and keep the stored config.ini format byte-identical.
       3. Update the affected tests.
Open:  Which fields get their own column (type, X, Y, value, wait, ...) and which stay in a
       combined details column?
