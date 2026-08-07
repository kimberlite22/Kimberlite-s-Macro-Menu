HAND-MAINTAINED. Never regenerated. See "Pending release lists" in CLAUDE.md.

Changes a Claude session just finished, staged here so the user can try them once before they move
to PENDING_RELEASE.md for the final pre-release check. Two lines per change with a blank line between
them, grouped by task group in the fixed order fixes, workflow, gui-ux, major:

    - <slug> - <one-liner>

      Review:

When there is something specific worth checking (a particular click-path to try, an edge case, a
config value to set first), an optional Notes: paragraph goes between the one-liner and Review:, same
blank-line spacing on both sides. Left out when the one-liner already says everything needed:

    - <slug> - <one-liner>

      Notes: <what to specifically test or look at>

      Review:

Leave one blank line between a change's own one-liner and its Review: line (or its Notes: paragraph
when present) as above, and two blank lines between one change's Review: line and the next change's
one-liner, so entries stay easy to tell apart when skimming the file.

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


- regen-overview-script - tasklist/OVERVIEW.md is now produced by `node tools/regen-overview.mjs`
  instead of by hand: it reads tasklist/open/ and tasklist/done/ and rewrites the file, including
  the group renumbering that used to need manual upkeep after every finished task.

  Notes: nothing to click-test in the app; check that the regenerated tasklist/OVERVIEW.md still
  reads sensibly (it also picked up several entries the manual process had missed, so it moved
  around more than a normal task-completion update would).

  Review:


- drop-legacy-release-exe-alias - release.yml no longer builds or publishes the second,
  pre-rename-named copy of the installer exe (Kimberlites-Anime-Expedition-Macro.exe); each release
  now ships exactly one installer asset (Kimberlites-Macro-Menu.exe) plus update.ini. Note: this was
  removed at your explicit request even though no real (non-prerelease) build has shipped the
  project-rename yet, so any install still on a pre-rename build will need a manual reinstall from
  the releases page instead of a smooth auto-update.

  Review:


## MAJOR

- stats-row2-three-columns - the Application Stats panel's row 2 is back to 3 evenly-spaced columns
  like rows 1 and 3 instead of 4: Screen Repetition Count is gone, and Session Time now sits in its
  place next to Step Repetition Count and Current Step Time.

  Review:


- background-session-engine-lifecycle - closing the GUI no longer stops an engine that runs in a
  different Windows session, so the macro can keep running in a background RDP session while the
  physical desktop is used for something else. First of four steps towards driving that whole setup
  from the app itself.

  Notes: needs your RDP Wrapper setup to test. Start the macro inside the background session, then
  open the GUI on the physical desktop: it should attach to that engine (status and counters live,
  Pause/Resume/Stop working) and show a blue "Background session" label next to the run state.
  Closing the GUI must leave the macro running; check with "query session" or Task Manager that the
  engine is still there. Pressing a capture button (F8 position, Map Placement, a step's region)
  must now fail immediately with "Capture failed: the engine runs in a background session..."
  instead of silently hanging for two minutes. On a normal single-session setup nothing should
  behave differently at all: no label, capture works as before, and closing the GUI still stops the
  engine.

  Review:
