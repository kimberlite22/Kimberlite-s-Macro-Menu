Title: no it doesnt automatically connect to roblox / When i press start the first time an error shows
       up (too fast to read) and then then session closes.
Prio:  1

Goal:  Starting a background session with "Boot straight into the macro" ticked actually opens
       Roblox into the configured private server, and does not show an error and close the session.

Files: gui/app/session_shell.py (run_session_shell, launch_game), gui/app/main.py (the
       --session-shell branch), <DataDir>\session_shell_log.txt (the new evidence source)

Steps: 1. BLOCKED ON EVIDENCE, do not guess. Read <DataDir>\session_shell_log.txt from the user's
          next Start with the box ticked. session-shell-diagnostics added it precisely for this,
          and the stay-connected change means the session's window is no longer disconnected a
          second after it appears, so an on-screen error can be read too.
       2. The log answers which of the two candidates it is. If the log stops before "launch
          target" then run_session_shell never reached launch_game and the failure is upstream (the
          engine start, the config read, or an exception in the shell itself, now captured by the
          sys.excepthook). If the log shows the launch being attempted and reporting success while
          Roblox never appears, then os.startfile's handoff through the default browser is what
          does not work in a session whose shell is not Explorer.
       3. For the second case the likely fix is to stop relying on the browser handoff and hand the
          share link to the Roblox protocol handler directly, or to start the default browser
          explicitly rather than through the shell "open" verb. Do not build that until the log
          says it is the actual cause.

Open:  - What the config held at the time of the first report is a red herring worth remembering:
         config.ini was written at 07:19 and the session tested ran at 07:04, so THAT run genuinely
         had no link configured. The retest afterwards did have one, and still failed, so this is a
         real second failure and not the same timing artifact.
       - Whether the user's own account is signed in to Roblox inside that session. A share link
         resolves server side and then hands off, so a session that is not signed in cannot land in
         the private server. Worth confirming before treating a clean log as a code bug.
