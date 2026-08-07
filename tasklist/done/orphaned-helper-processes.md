Title: Closing the app still does not reap the helper processes the engine spawned, so
       ocr_server.exe (and ocr_benchmark.exe) keep running forever. Observed live on 2026-08-07:
       four orphaned ocr_server.exe in a leftover Windows session, two of them started 4+ hours
       earlier from the PRE-RENAME install folder ("Kimberlite's Anime Expedition Macro"), i.e. they
       had survived both an app close and the rename. Only ending the whole Windows session cleared
       them. Known causes already established: StopOcrServer() in
       macro/tower_defense_macro_gui.ahk is dead code that nothing ever calls, and
       gui/app/engine_process.py's taskkill calls do not pass /T, so nothing kills the engine's
       child processes. This used to ride along with the engine-still-not-closing task, which is now
       in tasklist/done/, so the gap is currently untracked. Note gui-exe-lingers-first-launch only
       mentions ocr_server.exe as an analogy for PyInstaller's two-PID pattern, it does not cover
       this.
Completed: 2026-08-07
Commit:    daadfc0

Result: The engine had no OnExit handler at all, so StopOcrServer() was never called from any of its
        exit paths; it now registers OnExit(ReapHelperProcesses) next to OnError for the graceful
        case, and puts every spawned helper into a Windows job object with
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE for the taskkill /F and crash cases the handler cannot
        see. Adds StopOcrBenchmark() and a bounded KillProcessTree() so the exit callback cannot
        hang. The remote agent is deliberately left out of the job, since it is meant to outlive the
        macro.
