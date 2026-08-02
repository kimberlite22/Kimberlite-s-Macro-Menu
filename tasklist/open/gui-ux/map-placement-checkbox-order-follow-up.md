Title: Reverse die order also zuerst der text dann die checkmark damit es inline mti den anderen
       feldern im widget ist. Mach das auch bei anderen vorkommen gleicher muster.
Prio:  2

Goal:  Follow-up from map-placement-checkbox-order: the Map Placement tab's two checkboxes (custom
       tower slots, custom camera actions) show their label text first and the checkbox second
       (reversed from the current checkbox-then-text order), so they line up inline with the other
       label-then-field rows in the same widget. The same text-before-checkbox ordering is applied
       wherever else this checkbox-then-text pattern currently occurs in the GUI.
Open:  Which other occurrences count as "the same pattern" - a sweep of gui/app/*.py for QCheckBox
       instances currently placed before their own label text is needed to enumerate them before
       implementing, since the request generalizes beyond just this one tab.
