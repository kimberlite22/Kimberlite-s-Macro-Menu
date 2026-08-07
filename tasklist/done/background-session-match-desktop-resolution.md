Title:     you cant resize the window or you can but you cant fullscreen it the max size the window can
           reach is about a quarter of the fullscreen. It can go smaller but not bigger
Completed: 2026-08-07
Commit:    -

Result: The .rdp's desktopwidth/desktopheight now follow the primary display, resolved at runtime
through GetSystemMetrics (SM_CXSCREEN/SM_CYSCREEN) with a 1920x1080 fallback and both still
overridable by parameter for the tests. They were pinned at 1024x768, and mstsc will not let its
window grow past the session's own resolution, so on the reporting machine's 1920x1080 screen the
window topped out at 38 percent of the screen area and could only be made smaller. Smart sizing
scales what is drawn inside the window; it does not raise that ceiling, which is why the previous
fix alone did not answer this.

The size is the visible half of the problem, not the important one. Every macro coordinate is stored
as a percentage of the opening rectangle, and that rectangle is configured in absolute pixels on the
PHYSICAL desktop, so a 1024x768 session cannot even contain an opening measured on a 1920x1080
screen: a session that does not match the desktop is one where the macro's own geometry does not
fit. Matching the desktop is what makes the stored coordinates mean the same thing in both places.
"dynamic resolution:i:0" is kept, so the resolution is decided once at connection time and then
stays put, which is what stops those same coordinates being invalidated mid-run.

Deliberately not capped for very large displays. A 4K session costs more bandwidth and memory than
1080p would, but an arbitrary cap would silently reintroduce exactly the mismatch this fixes.

Verified with the full gui/ suite (434 passed) and by dumping the real generated file on the
reporting machine, which now reads desktopwidth 1920 and desktopheight 1080, matching its screen.
