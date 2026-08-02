HAND-MAINTAINED. Never regenerated. See "Pending release lists" in CLAUDE.md.

Changes a Claude session just finished, staged here so the user can try them once before they move
to PENDING_RELEASE.md for the final pre-release check. Two lines per change with a blank line between
them, grouped by task group in the fixed order fixes, workflow, gui-ux, major:

    - <slug> - <one-liner>

      Review:

Leave one blank line between a change's own one-liner and its Review: line as above, and two blank
lines between one change's Review: line and the next change's one-liner, so entries stay easy to
tell apart when skimming the file.

Fill in the Review: line yourself once you have tried the change, right here in the file, no chat
needed: a bare approval word and nothing else (approved / ok / okay / yes / lgtm) means it works, no
follow-up needed. Anything else, including an approval word plus more text ("approved, but X" does
NOT count), is read as a follow-up change to make in full, your own words, no particular format
required. The next /tasklist run resolves it: an approval moves the entry to PENDING_RELEASE.md, a
follow-up becomes a new task under tasklist/open/ (this line's text is its Title) and this entry is
dropped.

## WORKFLOW

- ci-automate-ocr-build - added .github/workflows/ci.yml, running OCR helper pytest plus a
  PyInstaller smoke build on every push/PR to main (not only on a version tag); release.yml and
  build-exe.yml are untouched, and gui.exe's build was deliberately left out of scope for now.

  Review:


- benchmark-ocr-engines - shadow-mode OCR comparison plus the experimental pre-release
  v0.4.16-dev2 to test it with (dev2 replaces dev1: same comparison, but the app now launches the
  benchmark helper for you instead of you having to run it yourself, see below). Install that
  release's Kimberlites-Anime-Expedition-Macro.exe (it installs over the normal one and keeps your
  config and presets), unzip ocr-benchmark-win64.zip from the same release page and move the
  ocr_benchmark folder it contains into your install directory
  (%LOCALAPPDATA%\Programs\Kimberlite's Anime Expedition Macro\ocr_benchmark\ocr_benchmark.exe) -
  a one-time step. From then on just run the app and press Start like normal; it starts the
  benchmark helper in the background automatically, no extra window to keep open. Play normally
  for about ten hours, then send back ocr_benchmark_log.jsonl from
  %LOCALAPPDATA%\Kimberlite's Anime Expedition Macro. Note: closing the app does not currently stop
  the benchmark helper (a known, separately tracked gap also affecting the OCR helper itself) - it
  is harmless to leave running, but check Task Manager if you want it fully stopped between
  sessions. The macro still acts only on the current Windows OCR result, the three other engines
  are only scored. Nothing auto-updates into this build: it is a pre-release, so the normal
  releases page and the in-app updater keep pointing at the real v0.4.16.

  Review:

