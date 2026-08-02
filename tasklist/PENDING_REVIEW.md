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
  v0.4.16-dev1 to test it with. Install that release's
  Kimberlites-Anime-Expedition-Macro.exe (it installs over the normal one and keeps your
  config and presets), unzip ocr-benchmark-win64.zip from the same release page and run
  ocr_benchmark.exe from that folder, then play normally for about ten hours; afterwards send
  back ocr_benchmark_log.jsonl from %LOCALAPPDATA%\Kimberlite's Anime Expedition Macro. The
  macro still acts only on the current Windows OCR result, the three other engines are only
  scored. Nothing auto-updates into this build: it is a pre-release, so the normal releases
  page and the in-app updater keep pointing at the real v0.4.16.

  Review:


## GUI-UX

- settings-search-follow-up-3 - re-investigated the "still stops accepting keystrokes" report; the
  settings-search-follow-up-2 NoFocus fix (c391e90) is verified sound on current main (full
  gui/tests/test_settings_search.py suite passes, including a real two-keystroke behavioral test),
  the report is release staleness: c391e90 was committed after the latest shipped tag v0.4.16, so no
  release contains it yet. No code changed.

  Review:


- general-parentheses-tooltips-follow-up-2 - re-investigated "still no tooltips" with new tests, not
  a repeat of the earlier stale-build call: ruled out the newly merged app-wide QLabel
  TextSelectableByMouse change (commit 2d442af) as a cause via two headless probes (a manual
  QEvent::ToolTip delivery and a stricter QTest.mouseMove-driven real hover simulation), both
  confirming tooltips still display correctly; also audited for event filters and a self-update
  silent-downgrade path, finding neither. No code bug found. If you still see no tooltip, please note
  here exactly which label/field you hovered and whether you are running an installed release, a
  locally built EXE, or `python app/main.py` from source, so a next round has something concrete to
  go on.

  Review:


- map-placement-checkbox-order-follow-up-2 - General tab Tower Loadout checkbox now follows label-first pattern

  Review:


- dropdown-chevron-indicator-revert - reverted the chevron override from QComboBox, restoring default arrow

  Review:


- keyboard-shortcuts-follow-up - removed question-mark icon from delete-confirmation dialogs

  Review:


- label-field-spacing-follow-up - increased label-to-field spacing from 10px to 13px

  Review:

