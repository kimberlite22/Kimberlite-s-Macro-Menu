Title:     Im tab general beim widget tower loudout der erste slot ist for some reason sehr breit,
           mach den in line mit den anderen feldern
Completed: 2026-08-01
Commit:    -

Result: In the General tab's "Tower Loadout" QGridLayout (gui/app/main_window.py), the "Number of
        placements:" label/spin box sat directly in grid columns 0/1 and the "Default slots..."
        label spanned only columns 0-1, so those two columns (and general_slots[0], which shares
        column 0 with the slot grid below) were sized to fit that text instead of the width of a
        combo box. Fixed by moving the label/spin box pair into their own QHBoxLayout spanning all
        ten columns, widening the "Default slots..." label's span to ten columns too, and setting
        equal column stretch (1) on all ten slot columns, so no single column is sized by content
        above it. Added a regression test asserting all ten general_slots widgets report the same
        width after window.show().
