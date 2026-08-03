Title: ok after a bit of testing the bug persist but only when i start the application for the
       first time after building, so i have reason to believe maybe the remaining process could be
       the updater or something in this direction. Another observation: closing the application
       takes atleast 1 second now which is moderatly inconvinient, so i would prefer to have the
       application closed faster, now that we have more info on the bug.
Completed: 2026-08-03
Commit:    -

Result: Closing the window was never actually guaranteed to end the process, because ending Qt's
event loop is not the same as ending the process and everything after it was outside the app's
control. gui/app/main.py now ends the process itself (run()/_terminate_process() with os._exit) once
the loop has returned and aboutToQuit has stopped the engine, instead of leaving that last step to
interpreter finalization with the best-effort update-check daemon thread still parked in urlopen().
gui/app/engine_process.py's shutdown is now bounded and fast: one shared 1.0 s budget instead of a
5 s wait three times over, taskkill runs with an explicit timeout, stop_engine_by_pid waits on a real
process handle instead of spawning tasklist.exe once per 200 ms poll, the escalation is taskkill
/T /F (tree, so the engine's ocr_server.exe helpers cannot be orphaned) with Popen.terminate()/kill()
kept only as a last resort, and the force-kill still rechecks the engine image name so a recycled PID
is never killed.
