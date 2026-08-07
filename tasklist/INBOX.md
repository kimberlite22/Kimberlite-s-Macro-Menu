Write new tasks here, one per line, any wording, any language. No format needed.
The Tasklist routine (see CLAUDE.md) sorts each entry into tasklist/open/<group>/ and plans it out.

Closing the app still does not reap the helper processes the engine spawned, so ocr_server.exe (and
ocr_benchmark.exe) keep running forever. Observed live on 2026-08-07: four orphaned ocr_server.exe in
a leftover Windows session, two of them started 4+ hours earlier from the PRE-RENAME install folder
("Kimberlite's Anime Expedition Macro"), i.e. they had survived both an app close and the rename.
Only ending the whole Windows session cleared them. Known causes already established: StopOcrServer()
in macro/tower_defense_macro_gui.ahk is dead code that nothing ever calls, and gui/app/
engine_process.py's taskkill calls do not pass /T, so nothing kills the engine's child processes.
This used to ride along with the engine-still-not-closing task, which is now in tasklist/done/, so
the gap is currently untracked. Note gui-exe-lingers-first-launch only mentions ocr_server.exe as an
analogy for PyInstaller's two-PID pattern, it does not cover this.
