Title:     also ich glaube der play ist die session zu disconecten, adde zwei buttons einen zum
           disconecten und zu showen der button im moment zum showen funktioniert nicht
Completed: 2026-08-10
Commit:    e7c9f1eaa8e8254f47c08210396c19b90cc2d2b4

Result: Show did not work because background_session_state.json still named session 6 while the
live background session was session 3, a reboot having renumbered them; the marker was the only
handle on the session, so Show, Stop and the status label all reported "not running". Added
resolve_background_session(), which falls back to adopting a live session on evidence (not this
session, not session 0, owned by exactly the same domain and account as this process, and running a
macro engine), failing closed at every step since Stop signs a session out, and refusing a marker
that names this process's own session. That also stopped Start from creating a second session
against an engine already running in the first. Added the Disconnect button next to Show, plus
disconnect_background_session() (idempotent only on DISCONNECTED) and one shared wait helper in
place of three copies. 618 gui tests pass.
