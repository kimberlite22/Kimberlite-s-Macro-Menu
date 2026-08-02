Title: CI-automate the OCR PyInstaller build outside a tagged release
Prio:  1

Goal:  macro/ocr_server.exe (and ideally gui/dist/gui.exe) build and get smoke-tested on every push/
       PR to main, not only on a pushed version tag, so a broken PyInstaller build or a broken
       ocr/tests/test_engine.py baseline is caught before a release rather than during one.
Files: .github/workflows/release.yml (the existing tag-triggered build, lines ~95-115 for the OCR
       exe: `pyinstaller --onefile --name ocr_server ... ocr_helper/cli.py`, then copied to
       macro/ocr_server.exe); a new .github/workflows/ci.yml (or similar) for the non-release
       trigger; ocr/pyproject.toml (dev extra already has pytest + pyinstaller).
Steps: 1. Add a new workflow triggered on `push`/`pull_request` to main (not `push: tags:` like
          release.yml), windows-latest runner (PyInstaller output is Windows-specific here).
       2. Run `pip install .[dev]` in ocr/, then `pytest` (covers test_engine.py's frozen-baseline
          check and test_protocol.py) before attempting a build, so a broken engine fails fast.
       3. Run the same `pyinstaller --onefile --name ocr_server ...` step release.yml already uses,
          verify ocr/dist/ocr_server.exe exists (reuse release.yml's existing Test-Path check), then
          discard the artifact (or upload it as a CI artifact, not a release asset) - this workflow
          only proves the build still works, it does not publish anything.
       4. Decide whether to fold the gui.exe PyInstaller build in too (release.yml's later steps) or
          leave that for a follow-up; keep this task scoped to the OCR build the "Deferred" note in
          CLAUDE.md originally referred to.
       5. Confirm release.yml itself is untouched: this is an additional, faster-feedback check, not
          a replacement for the tag-triggered release build.
Open:  -
