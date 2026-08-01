Title:     Bei dem map placement tab unter coordiantes fot his maps tower placement ist die box zu klein
           vertical gesehen mach das die dynamisch ist also sich anpasst wiviele slots ausgewählt sind, mach sie
           ausserdem weniger breit Der capture button ist viel zu breit
Completed: 2026-08-01
Commit:    -

Result: The Map Placement tab's tower-placement coordinates table now hides rows past the map's
effective slot count (map_num_placements when "Use custom tower slots" is checked, otherwise the
General tab's shared placement count) and resizes its height to fit exactly the visible rows via
setFixedHeight, instead of a fixed height unrelated to how many rows are actually in use. The table
columns got fixed, narrower pixel widths (90/70/70/90) instead of the Capture column stretching to
fill the whole table width, which is what made the Capture button far too wide; the whole box is now
added with left alignment so it hugs its narrower content instead of stretching across the tab.
