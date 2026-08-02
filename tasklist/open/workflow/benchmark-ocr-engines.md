Title: Benchmark alternate OCR engines against the current WinRT engine
Prio:  2

Goal:  Resolved scope (2026-08-02, replaces the original "written comparison" plan): build a
       shadow-mode experimental OCR helper that runs pytesseract, EasyOCR, and PaddleOCR alongside
       the current production winsdk/WinRT engine on every real detection during actual gameplay,
       logging all four results separately so they can be compared against each other and against
       the production result; then cut a one-off experimental pre-release (tag `v0.4.16-dev1` or
       similar) containing ONLY this task's changes so the user can run it on their own machine for
       real-world testing (~10 hours) and report back which engine(s) look worth pursuing further.
       No engine switch happens as part of this task; that decision waits for the user's test
       results.
Files: ocr/pyproject.toml (new optional-dependencies group for the three benchmark engines, kept
       separate from the `dev` extra so a normal production build never installs them);
       ocr/ocr_helper/engine.py (OcrEngine.recognize_image, line 56, already takes an already-
       captured PIL Image separately from recognize_region/_capture - the three alternate engines
       hook in at this same point, not by duplicating capture/upscale logic); new
       ocr/ocr_helper/engine_pytesseract.py / engine_easyocr.py / engine_paddleocr.py (or similar),
       each exposing the same `recognize_image(image) -> str` shape as a drop-in comparison engine;
       ocr/ocr_helper/cli.py (_run_server/handle_scan, lines 54-65 - shadow mode is an explicit
       opt-in flag, OFF by default, so the normal production binary this repo ships everywhere else
       is completely unaffected); a new results log next to the existing ocr_result*.txt files
       (e.g. macro/ocr_benchmark_log.jsonl, one line per detection with all four engines' text and
       timings); .github/workflows/release.yml (read-only reference) and a NEW workflow (e.g.
       .github/workflows/release-experimental.yml, workflow_dispatch-triggered) that builds this
       experimental variant and publishes it; gui/app/update_check.py (line 21,
       RELEASE_BASE_URL reads `releases/latest/download/...` - read this to understand why the
       experimental release must never become "latest", not to change it).
Steps: 1. Add pytesseract, easyocr, and paddleocr (plus their real runtime dependencies - the
          Tesseract OCR binary/its Windows packaging for pytesseract, paddlepaddle for PaddleOCR,
          torch/torchvision as EasyOCR's own dependency) to ocr/pyproject.toml under a distinct
          optional-dependencies group (e.g. `benchmark`), NOT the existing `dev` group, so a normal
          production build (and the existing release.yml run) never installs them.
       2. Add one thin wrapper class per alternate engine implementing `recognize_image(image) ->
          str` against the exact same already-captured, already-upscaled PIL Image
          OcrEngine.recognize_image (engine.py:56) receives, so all four engines see identical
          input and a difference in output is attributable to the engine, not to capture/upscale
          differences. The production OcrEngine class and its recognize_region/recognize_image path
          stay completely untouched.
       3. Add an explicit, default-OFF shadow-mode flag (CLI flag or env var) to cli.py's
          _run_server/handle_scan: when off (the normal production behavior, unchanged), behave
          exactly as today. When on, after computing the production result exactly as today, also
          run the three alternate engines against the same image and append one record (all four
          engines' recognized text plus each engine's own timing) to a new benchmark log file. The
          app must keep acting ONLY on the production winsdk result in both modes - the alternates
          are purely observational, never fed back into detection logic.
       4. Build the experimental release: a new workflow_dispatch-triggered GitHub Actions workflow
          that installs the `benchmark` extra, builds ocr_server.exe with shadow mode ON by default,
          builds gui.exe unchanged, and publishes both under a clearly experimental tag (e.g.
          `v0.4.16-dev1`).
       5. CRITICAL, verify this explicitly before considering the task done: the existing
          release.yml's publish step (`gh release create` around line 298) passes no `--prerelease`
          flag, so GitHub marks a release created that way as "latest" by default,  and
          gui/app/update_check.py's self-update path downloads from
          `releases/latest/download/...` (line 21) - if the experimental release were published the
          same way, EVERY existing installed user would silently auto-update to this experimental,
          much larger build. The new experimental workflow's publish step MUST pass `--prerelease`
          (or `--latest=false`) to `gh release create`, and you must confirm afterward, by checking
          the actual GitHub "latest" release, that it still points at the real production release,
          not the experimental one.
       6. Expect ocr_server.exe to become dramatically larger than today (EasyOCR/PaddleOCR each
          pull in a deep-learning framework on the order of a gigabyte); if the PyInstaller build
          becomes impractically slow/large for a GitHub Actions runner, that is a real finding to
          report back to the user, not something to silently work around by dropping an engine on
          your own judgment - ask first if it comes to that.
       7. Once published, give the user the direct release page/asset link (it will not appear via
          self-update or the "latest" alias) and stop there - this task's job is to get a testable
          build into the user's hands, not to judge the engines. Analyzing the ~10 hour test results
          the user reports back is a follow-up task once that data exists.
Open:  -
