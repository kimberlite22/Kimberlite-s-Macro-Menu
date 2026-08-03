Title: ok after a bit of testing the bug persist but only when i start the application for the
       first time after building, so i have reason to believe maybe the remaining process could be
       the updater or something in this direction. Another observation: closing the application
       takes atleast 1 second now which is moderatly inconvinient, so i would prefer to have the
       application closed faster, now that we have more info on the bug.
Prio:  1

Goal:  Follow-up from engine-still-not-closing: gui.exe still lingers after the main window closes,
       but only on the very first launch after a fresh build (the user suspects the update-check
       machinery, not the closeEvent sweep that was already fixed twice). Separately, closing the
       app now visibly takes at least about a second, which should be faster now that more is known
       about the underlying bug.
Files: gui/app/main.py (_schedule_update_check and its download thread, ~lines 68-159; the
       app.aboutToQuit wiring at ~lines 310-312 that calls stop_engine/stop_engine_by_pid),
       gui/app/engine_process.py (stop_engine/stop_engine_by_pid: taskkill.exe followed by a
       synchronous process.wait(timeout=5), ~lines 191-256), gui/app/main_window.py (closeEvent,
       already fixed twice for the lingering-process bug), gui/app/self_install.py (first-run
       install/extraction path, since the report is specific to "first time after building").
Steps: 1. Reproduce the first-launch-after-build lingering process (only with the user's explicit
          go-ahead per the CLAUDE.md hard rule against running the app, or by reasoning from code/
          log reading alone) and identify via Task Manager which exact process is left over
          (gui.exe, the AHK engine, or something the update check spawns) instead of assuming it is
          the updater.
       2. If it is the update-check daemon thread or its download thread (main.py's
          _schedule_update_check): check whether it performs any blocking network/file operation
          not interrupted by aboutToQuit, and make sure quitting does not wait on it.
       3. If it is specific to a fresh build's first run: check self_install.py's first-time
          install/extraction path for anything spawned only on that first run that is not covered
          by the same aboutToQuit cleanup as the normal engine process.
       4. Separately, address the now-noticeable close delay: stop_engine currently runs
          taskkill.exe then process.wait(timeout=5) synchronously on the Qt main thread during
          aboutToQuit; investigate whether the AHK engine can be signaled to exit faster (e.g. a
          dedicated quit command through the local bridge instead of taskkill) or whether the wait
          can be shortened without risking an orphaned engine process.
       5. Add/extend a gui/tests regression test for whichever root cause is found, following the
          existing test_closing_the_main_window_* pattern in gui/tests/test_main_window.py.
Open:  -
