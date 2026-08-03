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

## FIXES

- engine-still-not-closing - Closing the main window now actually ends the gui.exe process every
  time: the closeEvent sweep that closes every other open window no longer aborts partway through
  if one already-closed/deleted window raises an error, and closing the main window now explicitly
  quits the application instead of only hoping Qt notices every window is gone. Please try: use the
  app normally (open Edit Preset, Map Advanced, etc.), close the main window, and check Task Manager
  a few seconds later - no gui.exe process should remain.

  Review:


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


- drop-legacy-release-exe-alias - release.yml no longer builds or publishes the second,
  pre-rename-named copy of the installer exe (Kimberlites-Anime-Expedition-Macro.exe); each release
  now ships exactly one installer asset (Kimberlites-Macro-Menu.exe) plus update.ini. Note: this was
  removed at your explicit request even though no real (non-prerelease) build has shipped the
  project-rename yet, so any install still on a pre-rename build will need a manual reinstall from
  the releases page instead of a smooth auto-update.

  Review:


## GUI-UX

- general-parentheses-tooltips-follow-up-3 - Investigated (no code change) why tooltips are still
  reportedly missing in a locally-built gui.exe: confirmed the local PyInstaller invocation matches
  CI byte-for-byte, actually built gui.exe locally and confirmed every Qt plugin the tooltip
  mechanism depends on (qwindows.dll, Qt6Widgets.dll, Qt6Gui.dll, style.qss) is bundled correctly
  with no missing-module warnings, and re-audited main.py/widgets.py for any frozen-specific code
  path that could suppress tooltips - found none. This closes as a documented investigation: please
  try hovering over a field in your locally-built exe again and report back which specific field,
  how long you hovered, whether any tooltip anywhere works at all, and the PySide6 version your
  build resolved (`pip show PySide6` in gui/.venv) if it still does not show.

  Review:


- challenge-usage-option-label-cleanup - Removed the redundant "Option" header label from the Today's
  Challenge Usage grid in the Presets tab (gui/app/main_window.py:501); the three "Option 1/2/3"
  labels below it remain intact.

  Review:


## MAJOR

- project-rename - Renamed the project everywhere from "Kimberlite's Anime Expedition Macro" to
  "Kimberlite's Macro Menu" (code, GUI, docs, the branded release exe, and the GitHub repository
  itself, now at github.com/kimberlite22/Kimberlite-s-Macro-Menu), with a one-hop legacy-name
  migration for existing per-user installs and remote-agent MacroDir settings, and a temporary
  compatibility copy of the release exe under the old filename so already-installed builds' own
  self-updater is not stranded. The Roblox game's own name ("Anime Expedition") is unchanged, and
  the local checkout folder name is deliberately left unchanged (see the task's Result for why).

  Review:


- multi-game-support - The macro now supports multiple games, selectable from a new "Game" group
  at the top of the General tab (list + New/Rename/Delete + "Switch to Selected"). Each game has
  its own screens/presets/map placement/steps/timing settings; only disconnect support and the
  game-window settings stay shared across every game. An existing config is migrated automatically
  and safely on first launch into one default game ("Anime Expedition") - your presets and map
  profiles are preserved. Switching games persists the change and asks you to restart the app for
  it to take effect (a live in-place switch was deliberately out of scope, see the task's Result).
  Please try: creating a second game, adding a preset/map profile to it, switching to it (and
  restarting), then switching back - and confirm your existing presets/map profiles/settings are
  still exactly as they were before this update.

  Review:
