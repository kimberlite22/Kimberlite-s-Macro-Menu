Title:     no it doesnt automatically connect to roblox / When i press start the first time an error
           shows up (too fast to read) and then then session closes.
Completed: 2026-08-07
Commit:    -

Result: One root cause explained every symptom, and it was proven rather than guessed. The user's
screenshot of the error that had been flashing past read: "The system cannot find the file
specified. This initial program cannot be started: "C:\...\Kimberlite's Macro Menu\gui.exe"
--session-shell". Windows treats that whole string, quotes and argument included, as ONE file name,
because the RDP "alternate shell" value is handed to CreateProcess as the APPLICATION NAME, which
does no parsing. session_shell_command() built exactly that string, and its own docstring asserted
the opposite premise outright ("mstsc passes this string on to Windows as a command line"). The
shell therefore never started, Windows took the session down with it, and Roblox was never launched.

Confirmed with three live experiments using cmd.exe as a harmless stand-in, judged by whether
Explorer got replaced:

    unquoted, no arguments      -> alternate shell HONORED (Explorer replaced)
    quoted, no arguments        -> IGNORED, fell back to Explorer
    unquoted, WITH an argument  -> IGNORED, fell back to Explorer

and a fourth confirming that an unquoted path containing BOTH spaces and an apostrophe is honored,
so the install path was never the problem and the quoting it was supposed to protect was the thing
breaking it.

Since the value can carry neither quotes nor arguments, the mode can no longer be requested by a
flag. The installed app now gets a second executable NAME meaning "run as the session shell":
AEMSessionShell.exe, created next to gui.exe as a HARD LINK (so a second 85 MB file costs no disk)
with a copy fallback, and refreshed on every managed frozen startup rather than only at install
time, because self-install replaces gui.exe and a link made earlier would keep pointing at the
previous file. main.py infers the mode from its own executable's name before anything else happens,
so the existing early return still skips self-install, which as a session shell would relaunch and
log the session straight off. The --session-shell flag still works, since it costs nothing and keeps
the mode testable from a source checkout. session_shell_command() now returns the bare path, and its
docstring says plainly what it is and why a separate launcher exists at all.

Review caught one real hazard in the fallback: shutil.copy2 wrote straight to the launcher, so a
copy that failed halfway (a full disk) would leave a PARTIAL executable behind, and
session_shell_available only asks whether the file exists. Windows ends a session the instant its
shell fails to start, so that would have handed the user the very failure this task removes. The
copy now goes to a staging name and is renamed into place only once complete.

Verified with the full gui/ suite (441 passed) and by dumping the value that will actually be
written: a plain path, no quote characters, no arguments. The end to end confirmation that Roblox
then opens is the user's, since launching the macro engine to test is not permitted here; if the
session now boots into the control window and the engine but Roblox still does not appear, the next
suspect is os.startfile's browser handoff in a session whose shell is not Explorer, and
session_shell_log.txt (added by session-shell-diagnostics) will show whether the launch was
attempted and what it returned.
