Title: Remove that if a disconnect is detected the game tries to rejoin via opening the private
       server link instead of the old clicking a button. Remove that, and make it work the old way
       again.
Prio:  1

Goal:  A detected disconnect always recovers the way it did before the private server link was
       introduced: reactivate the game window, click the configured Reconnect button, restart the
       preset from its first screen. The link-based rejoin branch in CheckDisconnectTick is gone, so
       no disconnect ever hands off to the browser or teleports through a share link.

       The [General] PrivateServerLink setting itself STAYS. It has a second, unrelated consumer:
       the background session's "Start Roblox" button reads it (gui/app/session_shell.py:167, via
       read_config(...).general.private_server_link) and gui/app/roblox_launch.py reuses its
       validator. Deleting the field would break that button, so this task removes one CONSUMER of
       the setting, not the setting.

Files: macro/tower_defense_macro_gui.ahk: CheckDisconnectTick() (the privateServerLink branch at
       roughly lines 3450-3481, including the two waits it owns: the 30s wait for the game window
       when Roblox is gone entirely, and the 5s settle), and IsPrivateServerLink() at ~3390 (check
       whether anything else in the engine still calls it before deleting it; if nothing does, it
       goes too, and its "kept in step with validation_error() in gui/app/private_server_link.py"
       comment goes with it).
       gui/app/private_server_link.py, gui/app/roblox_launch.py, gui/app/session_shell.py: NOT
       changed, they are the consumers that keep the setting alive. Only re-read them to confirm
       that is still true.
       gui/app/main_window.py: the Private server link field's own tooltip/help text in the General
       tab's Disconnect Detection group, if it still describes disconnect rejoin as its purpose.
       Its wording is the only place a user would learn the setting still does something.
       gui/tests/test_main_window.py: any assertion pinning that tooltip text.

Steps: 1. Confirm the current behavior before deleting anything: read CheckDisconnectTick end to
          end and note that the else branch (ReactivateGameWindow, then ActClick on
          DisconnectReconnectX/Y, then Running := false plus DisconnectRestartPending := true) is
          the complete old path. It already exists and already runs whenever the link is empty or
          invalid, so this is a deletion, not a reimplementation.
       2. Delete the if/else around it: keep the else body unconditionally, and drop the
          privateServerLink lookup, the "rejoining through the configured private server link" log
          line, the Run call, both waits, and the "configured private server link was ignored
          because it is not a roblox.com https link" warning (there is nothing left to ignore).
          Leave the try/finally and DisconnectCheckBusy exactly as they are: that flag gates the
          watchdog's re-entry and a hand-cleared version of it is the bug the comment there warns
          about.
       3. Check whether IsPrivateServerLink() has any remaining caller in the engine. If not,
          delete it too rather than leaving a dead validator that claims to be kept in step with a
          Python function nobody compares it against anymore.
       4. Re-read the General tab's Private server link field text. If it advertises disconnect
          rejoin, reword it to describe what it actually still does (the background session's Start
          Roblox button), so the setting does not read as dead.
       5. Verify by reading, not by running: the engine must not be launched (see CLAUDE.md).
          Run python -m pytest -q in gui/ if step 4 touched any GUI text, and validate
          tower_defense_macro_gui.ahk rather than the include files on their own.

Open:  - Step 4's wording depends on whether the user wants the field to keep advertising itself at
         all now that its most visible use is gone. Reword it to name the Start Roblox button; if
         that reads wrong to the user, they can say so on the review line.
