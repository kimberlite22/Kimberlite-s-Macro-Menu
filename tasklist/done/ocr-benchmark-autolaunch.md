Title:     make it so i can just download the dev release and run the programm like normal and i
           collects test data for the three engines
Completed: 2026-08-02
Commit:    -

Result: Added EnsureOcrBenchmark() to macro/tower_defense_macro_gui.ahk, mirroring EnsureOcrServer():
        if the user has unzipped the release's ocr_benchmark folder directly into the install
        directory, the app now launches ocr_benchmark.exe hidden on every macro Start, with no
        separate program to run or console window to keep open; a normal production install never
        has that folder, so this is a silent no-op there. Re-cut the experimental release as
        v0.4.16-dev2 with updated release notes describing the new one-time setup. Investigated
        whether the launched helper gets cleaned up when the app closes: it does not - StopOcrServer()
        (the AHK-side graceful-stop function for ocr_server.exe) is already dead code, uncalled
        anywhere, and gui/app/engine_process.py's own taskkill calls never pass /T, so no child
        process the AHK engine spawns is currently reaped on close. This is the same gap
        tasklist/open/fixes/engine-still-not-closing.md already tracks and the user already asked to
        postpone; ocr_benchmark.exe inherits it unchanged rather than a new one-off fix being bolted
        on here. Documented plainly in the release notes and ocr/BUILD.md instead. The existing
        benchmark-ocr-engines PENDING_REVIEW.md entry was updated in place to describe the new
        v0.4.16-dev2 build and instructions rather than adding a second, redundant entry for the
        same not-yet-reviewed experimental build.
