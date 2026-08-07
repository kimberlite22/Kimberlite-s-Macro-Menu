Title:     Smart resizing doesnt work you have to enable it by rightclicking the window bar at the top.
Completed: 2026-08-07
Commit:    -

Result: The .rdp now carries "dynamic resolution:i:0" next to "smart sizing:i:1". Follow-up defect
of background-session-window-resize, which added the smart sizing line but left dynamic resolution
out of the file entirely. Out does not mean off: mstsc then uses its own default, which on current
Windows is dynamic resolution ON, and that takes precedence over smart sizing. The result was
exactly what was reported, smart sizing sitting inert until switched on by hand from the window
menu.

This does not weaken that earlier decision, it enforces it. That task deliberately did not want
dynamic resolution, because it changes the session's real resolution as the window is dragged while
every macro coordinate is stored as a percentage of a fixed opening rectangle. Omitting the key left
that decision to a default that happened to be the opposite of the one intended. The 0 is now
deliberate on both counts and the comment says so.

Verified with the full gui/ suite (434 passed) and by dumping the real generated file, which now
reads: screen mode id 1, smart sizing 1, dynamic resolution 0.
