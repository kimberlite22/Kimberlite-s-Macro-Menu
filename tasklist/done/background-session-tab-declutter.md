Title: Remove in background session den explanatory text completely und auch die sign in
       credentials (as far as i know they arent needed not sure tho atleast i never entered my
       password there and apparently it works just fine). Also remove the checkbox "boot straight
       into macro, with no windows desktop, that is already reflected in the second checkbox. The
       second checkbox should stay the same but with nothing in parantheses. And finally the log at
       the botton should be removed, the engine status if it is connected per background session
       should be displayed at the normal engine status at the top.
Completed: 2026-08-12
Commit:    -

Result: The Background Session tab lost its introductory paragraph, its whole "Sign-in credential"
group (username, password, Save/Forget Credential), the "Boot straight into the macro" checkbox and
the read-only message box at the bottom; "(administrator)" is gone from the no-desktop checkbox
label. Each removal had something behind it that had to be resolved rather than deleted. The account
now comes from the environment (the background session is a second logon of this account by
construction). With nothing left that can WRITE a credential, start_background_session no longer
refuses without one: mstsc asks for the password in its own visible window and remembers it there, so
the tab announces that instead of pointing at a button that no longer exists, and a headless Start
stays visible while Windows still has to ask. The credential write/delete API was deleted, leaving
credential_exists as a pure read. Booting into the macro is no longer optional (the best available
route is always taken), and the boot-mode line survives only for the one state the checkboxes cannot
show: neither route can start anything. The message box's contents moved under the tab's single status
line, rendered from state plus last action so the refresh at the end of every action cannot wipe the
message. The main window's "Background session" flag next to the engine status is now live: the tab
emits session_changed, and the status poll re-queries where the engine runs whenever the engine's
status file goes fresh or stale, which also catches a session started outside the app.
