Title:     in background session mach den current restore the windows default eine checkmark. Wenn
           man dann auf start drueckt dann soll erst das admin confirmation window kommen

Completed: 2026-08-07
Commit:    691718f41e8778de47cacc935d9eb0f4b1694ea7

Result: The "Enable no-desktop mode / Restore the Windows default" push button in the Background
Session tab is now a checkbox that only records intent, and the administrator confirmation window
comes with Start. _start_background_session applies the setting before it reads the boot route, so
the session comes up in the mode the box asks for rather than the one the machine was in a moment
earlier; nothing is elevated when the machine already matches the box, so a repeated Start raises no
prompt. A declined prompt is reported and then ignored, since a session with a desktop still works
and refusing the elevation must not cost the user their session; its message is kept in front of the
session result rather than overwritten by it. Two sync rules keep the box honest: it follows the
machine only when the machine itself moved (so a re-check cannot undo a pending tick), and a render
that could not show the box at all remembers nothing (so a first render without an installed shell
executable cannot leave the box unchecked while the machine is switched on, which Start would have
read as a request to switch it back off). rdp_wrapper's success message dropped its now-false "Start
it again to use the new mode." sentence.
