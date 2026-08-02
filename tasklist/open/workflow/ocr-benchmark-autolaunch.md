Title: make it so i can just download the dev release and run the programm like normal and i
       collects test data for the three engines
Prio:  1

Goal:  Follow-up from benchmark-ocr-engines: the experimental v0.4.16-dev1 release currently
       requires the user to separately double-click ocr_benchmark.exe and keep its console window
       open for the whole session, alongside running the app normally. Make the app itself launch
       and manage ocr_benchmark.exe automatically, so the user's only manual step is a one-time
       unzip; every normal run after that just works like the regular app.
Files: macro/tower_defense_macro_gui.ahk (EnsureOcrServer/StopOcrServer at ~1372-1433 are the
       pattern to mirror; OcrServerPid global at ~1100; the EnsureOcrServer() call at ~3151 is
       where engine startup already happens), ocr/ocr_helper/benchmark_runner.py (STOP_FILENAME =
       "ocr_benchmark_stop.txt", already supported, ~line 16 and the run() loop at ~168-180),
       .github/workflows/release-experimental.yml (release notes text at ~287-324 describing the
       current two-step manual process; the ocr_benchmark packaging step at ~438-470 already
       produces a folder literally named ocr_benchmark inside the zip).
Steps: 1. Add EnsureOcrBenchmark(), mirroring EnsureOcrServer(): check for
          `RuntimeDir "\ocr_benchmark\ocr_benchmark.exe"` (the fixed location the user is told to
          unzip the release's ocr_benchmark folder into, directly inside the app's install
          directory); if missing, no-op (this keeps the change completely inert for every normal
          production user, who will never have this file). If present and not already tracked
          running, launch it hidden with `--dir "<DataDir>"` explicitly passed (matching
          EnsureOcrServer's style even though benchmark_cli.py can also auto-detect it), track the
          PID in a new OcrBenchmarkPid global.
       2. Call EnsureOcrBenchmark() once at the same engine-startup point EnsureOcrServer() is
          already called (~line 3151), not on every OCR request - unlike the OCR server there is no
          per-detection lazy-start need.
       3. Verify empirically whether ocr_benchmark.exe, launched as a child of the AHK engine
          process the same way ocr_server.exe already is, actually gets reaped when the app closes
          (StopOcrServer() exists but is currently uncalled anywhere in the codebase, so ocr_server.
          exe's own cleanup path is apparently an external process-tree kill from gui.exe's
          engine_process.py, not this function) - test with a cheap stand-in exe/script rather than
          the real multi-gigabyte bundle. If orphaning does happen, add a StopOcrBenchmark()
          mirroring StopOcrServer()'s graceful-stop-file (benchmark_runner.py already supports
          `ocr_benchmark_stop.txt`, see STOP_FILENAME) plus force-kill fallback, and wire it into
          whatever the real (not the apparently-dead StopOcrServer) shutdown path turns out to be.
       4. Update release-experimental.yml's release notes text (~287-324) to describe the new
          one-time setup (unzip the ocr_benchmark folder into the install directory once) instead
          of "run ocr_benchmark.exe and keep its window open for the whole session"; update
          ocr/BUILD.md's equivalent instructions too.
       5. Re-cut the experimental release under a new tag (e.g. v0.4.16-dev2) via
          release-experimental.yml so the user gets a build with this fix; do NOT reuse v0.4.16-dev1
          per the tag-reuse issue already hit once during the original release (see git history on
          the benchmark-ocr-engines PR). Re-verify, exactly as before, that the new tag publishes as
          a pre-release and the repository's "latest" release is still the real v0.4.16 - this is
          the same safety requirement from the original task, it applies to every experimental
          publish, not just the first one.
Open:  -
