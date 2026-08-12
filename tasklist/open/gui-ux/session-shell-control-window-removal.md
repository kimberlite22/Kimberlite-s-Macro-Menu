Title: When opening the background session there is little windows that pops up to fix the session
       from inside. Remove it, and migrate the button start explorer to the main macro window
Prio:  4

Goal:  Opening the background session no longer puts a control window on top of it, and the "Start
       Explorer" escape hatch is reachable from the main macro window on the physical desktop
       instead. The window is SessionShellWindow in gui/app/session_shell.py (built by _build_ui at
       :345; the buttons are "Start Roblox", "Start Explorer" at :368 and "Sign out"), and it
       appears in BOTH background session modes: as the session's shell it is always on top with no
       minimize or close button (:320-:329), and alongside Explorer it is an ordinary window
       (:336-:343).

       Two things have to be answered before this is a deletion rather than a breakage, and both are
       in Open: below. The window is not only a control panel, it is also the shell PROCESS in
       shell mode, and "Start Explorer" is deliberately an INSIDE-the-session action that the main
       window, running in a different Windows session, cannot simply call.

Open:  - What becomes the session's shell once the window is gone? In shell mode this process IS the
         shell (see the module docstring at :7-:20): its own comments state that the window closing
         ends the last window and therefore the event loop, which logs the session off. Removing the
         window without replacing that role would end the background session the moment it starts.
         An invisible/hidden shell process that keeps the event loop alive is the obvious answer,
         but confirm it against gui/app/main.py's session_shell_mode startup path rather than
         assuming it.
       - How does a "Start Explorer" button in the main macro window reach the OTHER session?
         start_explorer() at :247 is a plain subprocess.Popen(["explorer.exe"]) in the calling
         process's own session, so the same call made from the main window would open Explorer on
         the physical desktop, which is not what the button is for. Reaching into the RDP session
         needs a cross-session mechanism (a command through the existing bridge files that the
         in-session process acts on is the cheapest one, since a process already runs there). Decide
         this before writing any UI.
       - "Start Roblox" and "Sign out" share the window being removed. The task text only names
         Start Explorer, so decide explicitly whether those two also move, disappear, or already
         have equivalents in the main window's Background Session tab (Stop there already ends the
         session).
       - Coordinate with the in-flight branch worktree-background-session-tab-declutter, which is
         reworking the Background Session TAB in the main window (INBOX line about removing its
         explanatory text, credentials, a checkbox and the log). That is a different window from
         this one, but this task wants to ADD a button to the same tab, so check where that branch
         landed before starting.
       - workflow/remove-session-shell-launcher-deadweight also edits gui/app/session_shell.py, for
         the launcher exe rather than this window. Neither blocks the other, but expect a conflict
         in that file if both run at once.
