Title:     CI-automate the OCR PyInstaller build outside a tagged release
Completed: 2026-08-02
Commit:    -

Result: added .github/workflows/ci.yml, triggered on push/pull_request to main, which installs
ocr/'s dev extra, runs pytest (test_engine.py's frozen-baseline check plus test_protocol.py), builds
the OCR helper with the same PyInstaller command release.yml uses, verifies ocr/dist/ocr_server.exe
was produced, and uploads it as a short-retention CI artifact; release.yml and build-exe.yml are
untouched. Scoped to the OCR build only, gui.exe's PyInstaller build was left out of this workflow
(build-exe.yml already covers a full manual build+artifact upload of gui.exe; folding it into this
push/PR-triggered workflow too is left for a follow-up if faster feedback on the GUI build is wanted).
