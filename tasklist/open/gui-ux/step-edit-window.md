Title: Die step edit settings in ein neues window machen
Prio:  4

Goal:  The "Step Editor" group box moves out of the Edit Preset window into its own secondary
       window, so Edit Preset itself only shows the screens list, the steps table and the
       preset-level boxes. Editing a step opens that window instead of scrolling down to a form
       wedged under the table.
Open:  What opens the window: double-clicking a step row, a dedicated "Edit Step..." button, or
       both, and does "Add Step" open it empty as well? Modal or independent, and can it stay
       open while the user clicks through several rows in the table? Where do "Add Step" /
       "Update Selected" / "Delete Selected" / "Duplicate" live afterwards, still under the
       table in Edit Preset or as Save/Cancel inside the new window? The step editor's own
       secondary windows (Configure Outcomes, Set Position capture, Test OCR) would then be
       opened from a window that is itself secondary; check that against
       [[engine-still-not-closing]], since a window nested one level deeper is exactly what
       kept gui.exe alive before.
