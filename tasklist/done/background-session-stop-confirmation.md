Title:     Stop doesnt stop the session and it also says background session: not running maybe it lost
           the session after it had startet
Completed: 2026-08-07
Commit:    -

Result: Both halves of the report were real, and they had different causes.

"Stop doesn't stop the session": WTSLogoffSession is called with bWait false, so it returns as soon
as the request is ACCEPTED, not when the session is gone. stop_background_session treated that
instant true as success, cleared the marker and reported "Background session stopped." while the
session was still listed. Reproduced directly against a live session: Stop returned ok=True and the
very next enumeration still showed the session. It now confirms the logoff the same way the Start
path already confirms its disconnect (see that path's "returning true only means the request was
accepted" comment), polling until the session is really gone, pumping Qt events through the same
optional pump callback the tab already passes to Start.

"It says background session: not running": that was the same bug's second effect, and the worse
one. Clearing the marker on an unconfirmed logoff strands the session permanently, because the
marker is the only handle the app has on it: the tab then reports "not running" and Stop answers
"No background session is currently running" while a real session keeps running. On a failed or
unconfirmed logoff the marker is now KEPT, so Stop can simply be pressed again.

A third path to the same orphaned state was found while testing and fixed too: Start's claim loop
could time out while the session came up moments later, leaving a live session with no marker ever
written. On the timeout path Start now sweeps once for a new, owner-matching session and adopts it
(marker written, disconnect attempted) so it stays stoppable, reporting honestly that it came up but
could not be confirmed in time. Zero, non-matching or MULTIPLE candidates keep the old behavior
untouched, since adopting the wrong session is worse than leaving them alone. Review caught that the
first version read the candidate's owner twice; a transient failure on the second read would store
an empty domain that _owner_is can never match, so Stop would refuse the very session this branch
exists to keep stoppable. The owner is now read once and the same value is both matched on and
stored.

The logoff confirmation budget is its own constant (30s) rather than reusing the disconnect's 10s.
Dropping a client is nearly instant, but a logoff tears down a whole desktop's worth of processes.
Measured on the reporting machine: a plain Explorer session finished logging off about twelve
seconds after the request, which the 10s budget reported as a failure even though the logoff was
working perfectly. That measurement is in the constant's comment.

Also fixed on review: the tab's Stop now disables the session buttons for the duration, exactly as
Start already did. Pumping Qt events to keep the window responsive also lets a second click land
inside the call, and a Start reaching in there could have its brand new session's marker cleared by
the stop still finishing.

Verified with the full gui/ pytest suite (425 passed) and end to end against real Windows sessions:
Start claims and disconnects, Stop returns only once the session is genuinely gone (4.1s in the
final run, against an instant-and-still-there before), the marker is cleared only then, and no
session is left behind. The failure path was observed for real too, before the budget was raised:
Stop gave up at 10.25s, correctly kept the marker, correctly reported "could not be confirmed
stopped. Try Stop again.", and the session finished logging off about two seconds later.
