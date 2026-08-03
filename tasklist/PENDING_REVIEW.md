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

## FIXES

- engine-still-not-closing-followup - the app now ends its own process the moment the main window
  closes, instead of leaving that last step to Python's own shutdown while the background update
  check is still running, and the engine shutdown it does on the way out is bounded to about a
  second instead of up to fifteen.

  Notes: two things to check. First, the linger: build as usual and start that fresh build for the
  first time (the launch that installs itself and relaunches, which is the one that used to leave
  gui.exe behind), then close the window and watch Task Manager for a gui.exe that never
  disappears. Worth repeating a few times, and worth also closing the window very soon after it
  appears, since that is when the update check is most likely to still be in flight. Second, the
  speed: closing should now take clearly less than the second it did before. This one could not be
  reproduced here (running the app needs your explicit go-ahead, and this session had no way to ask
  for it mid-run), so it was fixed from the code alone: if a gui.exe still lingers after this,
  please say what else happened during that launch, in particular whether an update prompt or
  download dialog appeared.

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

- settings-search-follow-up-4-confirmed - Your "Yes works as intended" review of
  settings-search-follow-up-4 wasn't an exact match against the fixed approval-word list, so it went
  through as a follow-up task per the routine's own strict-matching rule; checking it before
  planning any work showed there was nothing left to do, since your own words already confirm the
  fix works. Closed with no code change. No action needed unless you disagree.

  Review:


## MAJOR

- project-rename-followup-local-folder - Re-confirmed rather than acted on: renaming the local
  checkout folder itself stays a manual step for you to do yourself once no session is active in
  it, exactly as project-rename's own Result already said, since this checkout is the live working
  tree for multiple concurrent sessions. No action needed unless you want this reconsidered.

  Review:
