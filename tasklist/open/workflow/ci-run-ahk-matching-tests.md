Title: Run macro/tests/test_ocr_matching.ahk in CI
Prio:  2

Goal:  The OCR matching test table runs on every push and pull request like the ocr/ pytest suite
       does, so a change to the matching rule cannot merge with the table red. Today it only runs
       when someone remembers to run it locally.
Open:  .github/workflows/ci.yml already uses windows-latest, but that runner has no AutoHotkey.
       Installing one is the whole question: "choco install autohotkey.portable" pins a v1/v2
       choice that has moved before, and a CI job that fails for a reason unrelated to the change
       under test is worse than no job. Options are pinning an exact portable version, downloading
       the release zip from GitHub directly, or caching it. Also decide whether it is its own job
       or a step in the existing ocr-ci job (it needs no Python, so its own job is cleaner).
       The script already exits with the failure count, so the gating itself needs nothing.
