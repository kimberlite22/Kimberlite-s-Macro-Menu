Title: Restart the application automatically after switching to selected, and for some reason
       currently i dont need to restart the application for it to be in effect atleast the presets
       displayed match the game.
       After a bit of testing: the changes get displayed but are not acitve wich is quite
       unintuative, either dont display them or display them but without the game needing to
       restart, this gets kind of fixed with the initial first proposal of restarting the game
       immidiately but do it anyways when there might me a delay to restarting or something. If
       before restarting your changes are not saved to config.ini prompt and ask if you want to
       restart before saving.
Prio:  1

Goal:  Follow-up from multi-game-support: "Switch to Selected" (gui/app/main_window.py's
       _switch_game) currently only writes config.ini and refreshes the GUI's own displayed data,
       then tells the user to restart manually - the AHK engine's ActiveGameName is resolved once
       at startup and stays fixed for the process's lifetime (InitGames() in
       tower_defense_macro_gui.ahk), so the GUI ends up showing the newly selected game's presets/
       map profiles while the engine is still actually running the previous game, which the user
       found confusing. Switching now restarts the engine automatically instead of leaving that to
       the user, closing the display/engine mismatch by construction; unsaved changes are saved-or-
       discarded via a prompt before the restart happens, and the restart shows a busy state rather
       than looking idle while it is in progress.
Files: gui/app/main_window.py (_switch_game, ~lines 1256-1277; _refresh_config), gui/app/main.py
       (the engine Popen/PID is currently local closure state inside the startup function, not
       owned by MainWindow, which is exactly what the task's own Result already flagged as the
       reason a live restart was out of scope the first time), gui/app/engine_process.py
       (stop_engine/stop_engine_by_pid, launch_engine_hidden, wait_for_engine_ready - the same
       helpers main.py's own startup already uses, meant to be reused here rather than duplicated),
       macro/tower_defense_macro_gui.ahk (InitGames(), the actual architectural reason a live
       in-place switch needs a real engine restart instead of just a config write).
Steps: 1. Give MainWindow (or a small controller object it owns) real ownership of the engine
          process lifecycle instead of leaving the Popen/PID as closure-local state inside
          main.py's startup function, so a restart can be triggered from _switch_game.
       2. Before restarting, check the same dirty/unsaved-changes state the app already tracks for
          its own Save button; if there are unsaved changes, prompt the user to save or discard
          before restarting (per the user's explicit ask), instead of restarting into a config.ini
          that silently drops their in-progress edits.
       3. Make _switch_game restart the engine automatically right after the config write succeeds:
          stop the current engine (stop_engine/stop_engine_by_pid) and relaunch it the same way
          main.py's startup does (launch_engine_hidden + wait_for_engine_ready), reusing
          engine_process.py's existing helpers.
       4. Show a busy/progress state for the duration of the restart (reusing the same
          wait_for_engine_ready polling pattern main.py's startup already uses to keep Qt
          responsive) instead of leaving the window looking idle and interactive mid-restart, and
          disable further game switches until it completes.
       5. Update gui/tests to cover: switching now restarts the engine automatically, unsaved
          changes trigger the save-or-discard prompt first, and the GUI's displayed active game can
          no longer show a game the engine has not actually switched to yet.
Open:  -
