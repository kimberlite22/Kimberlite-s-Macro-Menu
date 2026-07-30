Title: Jeder checkmark soll auch ein checkmark sein nicht einfach nur ein ausgefüllter kasten
Prio:  5

Goal:  Checked checkboxes show a real check glyph instead of a filled square, everywhere in the
       GUI.
Files: gui/app/widgets.py (QSS for the checkbox indicator), assets/
Steps: 1. Style the checked indicator with an actual check mark, covering the hover, disabled and
          partially-checked states.
       2. Apply it to checkable list/table items too, not only standalone checkboxes.
Open:  -
