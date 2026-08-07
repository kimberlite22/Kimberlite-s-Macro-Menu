Title:     Ausserdem soll roblox automatisch fullscreen sein nicht mehr in der alten bilschiratio weil
           wir den platz fuer die ui ja nicht mehr brauchen. Die ui soll dann in die pyhton gui aber
           das koennen wir auch spaeter verschieben.

Completed: 2026-08-07
Commit:    5109e5226631e019975aee1b8e421431d6daaa26

Result: A new [General] FullscreenOpening option, a checkbox in the General tab's Game Window group,
makes the opening the whole screen. It is applied in exactly one place, GetHoleRect(), which is
where every consumer already reads the opening from, so the percent conversions, the window pin and
its lock, and the gray overlay (whose four bars come out zero-sized and draw nothing) all follow
without knowing about the option. A_ScreenWidth is also the right answer inside a background RDP
session, since the engine there reads that session's own screen. Stored coordinates are NOT
migrated and do not need to be: they are percentages of the opening, and 1248x702 and 1920x1080 are
both 16:9, so every saved position points at the same place. The window's title bar and resize frame
are stripped so the picture really fills the screen, and the way back is written to disk BEFORE the
change rather than held in a variable: the game outlives the engine, so a crash between stripping
the frame and putting it back would otherwise leave a window with no title bar and nothing anywhere
that knows what it had, since a later engine cannot tell "we took its frame away" from "it never had
one". Hence the frame is only stripped once the marker reached disk; the marker carries the process
name so a recycled handle costs a missed restore rather than a caption on an unrelated window; an
unparsable marker is deleted rather than retried forever; and the restore runs at startup, on lock
release, on exit, and from the lock timer, which is what lets unticking the option put the frame
back mid-run. The lock timer also re-applies the borderless style, so a game window restarted under
a running macro cannot come back with a title bar, and SetWindowPos with SWP_FRAMECHANGED follows
every style change so Windows actually recomputes the non-client area. The four opening values grey
out but are kept while the screen is used, since unticking has to give them back. Open questions
resolved by the user: borderless full-screen rather than Roblox's own fullscreen mode (which cannot
be positioned by WinMove and would fight the window lock). The user's own note that moving the
remaining UI into the Python GUI is a later step was left out of scope, as they asked.
