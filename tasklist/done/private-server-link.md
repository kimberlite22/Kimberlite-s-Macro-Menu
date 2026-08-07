Title:     Man soll ein link für ein private server pasten können dem automatisch gejoined wenn man
           disconnected wird

           Wenn es geht dann mach es so das die externe session started direkt das roblox mit dem link
           sich öffnet. Dann kann man das macro starten.
Completed: 2026-08-07
Commit:    -

Result: A "Private server link" field in the General tab's Disconnect Detection group persists to
[General] PrivateServerLink, and the engine's auto-reconnect uses it: when the field holds a valid
link, CheckDisconnectTick launches it instead of clicking the configured Reconnect position, then
falls into the existing DisconnectRestartPending path completely unchanged. An empty field keeps
today's click behavior exactly, in both places.

The open question is answered: the current reconnect never relaunches Roblox, it clicks a
configured screen position (DisconnectReconnectX/Y) and restarts the preset from its first screen.
So the link replaces that one click and nothing underneath it had to change.

Step 5 needed no new launching code. Checking before planning (tasklist routine step 4) showed
background-session-minimal-shell had already built both halves: gui/ipc/config_reader.py already
read PrivateServerLink, and gui/app/session_shell.py already launched it inside the session shell.
Only the settings field feeding them was missing, which is what that task's own note predicted.
The scope limit is stated in the field's tooltip rather than glossed over: only the "Boot straight
into the macro" shell path opens Roblox automatically, because a background session running the
normal Windows desktop offers no way to start a process inside it.

Validation is shared rather than GUI-only, because gui/app/session_shell.py hands the link to
os.startfile and the engine hands it to Run, so both are launch boundaries that must not trust a
hand-edited config.ini. New gui/app/private_server_link.py holds the Python validator (https only,
a roblox.com host matched at a DNS label boundary, and either the share form or the older
privateServerLinkCode form, each with a non-empty code); IsPrivateServerLink in the AHK engine is
its deliberate counterpart. The link is never written to the log in any branch, including the
warning logged when a configured link is rejected.

Four defects found by review were fixed rather than accepted: launch_game reached os.startfile("")
because the validator treats empty as valid (it means "not configured" there, but "launch nothing"
here, so empty needed its own refusal); the post-launch wait watched for any game window, which the
still-open Roblox disconnect dialog satisfied instantly, so it now waits for the window only when
Roblox is actually gone and otherwise applies a short settle, with a comment stating plainly that
neither wait detects the server having finished loading (the restarted preset's own screen
detection does that, exactly as on the click path); and the AHK guard accepted any roblox.com https
URL, which is now tightened to match the Python validator on path, case and non-empty codes.

Verified without launching the app (CLAUDE.md hard rule): AutoHotkey64.exe /validate parses the
engine cleanly, an 18-case throwaway probe script confirms IsPrivateServerLink behaviorally
(including the security-relevant rejections roblox.com.evil.example, http, file:// and a bare exe
path) rather than by reading the regex alone, and the full gui/ pytest suite passes.
