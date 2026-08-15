Title: When opening the background session there is little windows that pops up to fix the session
       from inside. Remove it, and migrate the button start explorer to the main macro window
Completed: 2026-08-15
Commit:    -

Result: SessionShellWindow is gone and the background session now runs headless. Removing it needed
an answer to what kept the session alive: the WINDOW never did, the event loop does, and Windows
only logs a session off when its shell PROCESS exits, so run_session_shell simply stops building a
window and both modes set setQuitOnLastWindowClosed(False) so no transient dialog can end the loop.
The escape hatch moved across the session boundary through a new file channel,
gui/app/session_commands.py, built like the macro's other bridges (atomic .tmp plus os.replace, a
token, consume-on-read by rename) and served by a 500ms QTimer in the process already running inside
the session, which is what avoids needing administrator rights to start a process in another session.
The Background Session tab gained an "Inside the background session:" row with "Start Explorer" and
"Start Roblox": each refuses when no session is running, then waits about six seconds for the
matching ack and renders the session's own answer. "Start Roblox" moved too rather than being
dropped, because it had no equivalent anywhere else and Roblox closed inside the session could
otherwise only be recovered by restarting the whole session; "Sign out" did not, since Stop in the
same tab already ends the session, and sign_out_this_session went with the window. Crossing a session
boundary brought back one hazard a button inside the session never had, a request outliving the
session it was aimed at, and three things answer it: a command names the Windows session id it is
for and is refused anywhere else, it carries the moment it was written and expires after 60 seconds,
and both the caller giving up and Stop withdraw an unanswered request outright. So a file nothing
claimed can never be carried out by the next background session that happens to start. The two
new buttons answer to both gates that can hold them (a session action running here, an unanswered
command of their own) through one method, so neither hands back a button the other still holds. The
Explorer fallback survives, now keyed on the command channel failing to install rather than on the
window failing to build: as the shell, a session with a normal desktop is still a far better failure
state than one that signs itself out.
