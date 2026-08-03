AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead
(see "Tasklist routine" in CLAUDE.md). A stale OVERVIEW.md next to accurate task files is not a
conflict worth resolving by hand, just regenerate it.

Last regenerated: 2026-08-03 (after completing window-title-version-indicator)

## FIXES

(none open)

## WORKFLOW

(none open)

## GUI & UX

1. [general-parentheses-tooltips-follow-up-5](open/gui-ux/general-parentheses-tooltips-follow-up-5.md)
   - fifth round on "no tooltip ever shows": the user confirmed a freshly rebuilt exe still shows no
   tooltips and Windows's own settings look normal, but the exact PySide6 version and a plain source
   run are still untested.

2. [screen-detection-settings-placement](open/gui-ux/screen-detection-settings-placement.md) - BLOCKED:
   the "Screen Detection" group box this task targets no longer exists in the code (part of
   screen-detection-overhaul, currently reverted); cannot proceed until that major task lands.

## MAJOR

1. [multi-game-support-restart-ux](open/major/multi-game-support-restart-ux.md) - Follow-up from
   multi-game-support: "Switch to Selected" restarts the engine automatically instead of leaving the
   GUI showing a game the engine has not actually switched to yet, with a save-or-discard prompt
   first if there are unsaved changes.

2. [detailed-stats-follow-up](open/major/detailed-stats-follow-up.md) - Follow-up from
   detailed-stats: drop the Time Breakdown overlay's Step Time table, show the active step's
   accumulative time in the Application Stats panel instead, and grow the Screen Time table into
   the freed space.

3. [screen-detection-overhaul](open/major/screen-detection-overhaul.md) - a screen becomes
   self-identifying: its own entry detection, then its steps, then a global detection picks the
   next screen, with per-screen defaults resolving ties instead of step order.

4. [global-screens](open/major/global-screens.md) - screens are defined once globally instead of
   being duplicated inside every preset; only the step sequence run on each screen stays
   preset-specific.

5. [ocr-expected-variants](open/major/ocr-expected-variants.md) - an "expected text" field holds
   several independent variants, each checked separately, plus a button that adds the
   just-recognized text as a new variant.

6. [private-server-link](open/major/private-server-link.md) - a stored private server link is used
   to rejoin after a disconnect instead of the normal public rejoin; empty field keeps today's
   behavior.

7. [remote-agent-tab-online-settings](open/major/remote-agent-tab-online-settings.md) - the "Remote
   Agent" tab becomes "Online Settings", trimmed to sign-in and pair, with the agent path detected
   automatically and the server URL fixed. Explicitly deprioritized by the user.

8. [rapidfuzz-fuzzy-matching](open/major/rapidfuzz-fuzzy-matching.md) - OCR expected-text matching
   uses a real edit-distance score instead of a fixed-length substring-window heuristic.

9. [opencv-template-matching](open/major/opencv-template-matching.md) - screens and steps can be
   detected by OpenCV template or color matching, for cases text recognition handles poorly.

10. [agent-self-update-codesigning](open/major/agent-self-update-codesigning.md) -
    animeexpedition-agent.exe updates itself automatically instead of needing manual distribution,
    without SmartScreen warnings. Blocked on a code-signing certificate.

## DONE (newest first)

- 2026-08-03 [window-title-version-indicator](done/window-title-version-indicator.md) - The main window's title bar now shows "APP_NAME vX.Y.Z" with build provenance: no suffix for an official release, " (local build)" for a locally built exe (new release-only RELEASE_BUILD marker written by release.yml), or " (source)" for a plain source run; falls back to the bare app name if VERSION can't be read (commit -)

- 2026-08-03 [general-parentheses-tooltips-follow-up-4](done/general-parentheses-tooltips-follow-up-4.md) - Fourth round on "no tooltip shows": AskUserQuestion is not available to the delegated subagent working this task, so the planned interactive Steps 1-3 could not run; forwarded the three questions to the user instead. Closes as a documented investigation, no code change (commit -)

- 2026-08-03 [engine-still-not-closing-followup](done/engine-still-not-closing-followup.md) - Closing the window never actually guaranteed the process ended: main.py now ends it itself once the event loop returned and aboutToQuit stopped the engine, instead of leaving that last step to interpreter finalization with the update-check daemon thread still parked in urlopen(), and the engine shutdown itself is now bounded to about a second instead of up to fifteen (commit -)

- 2026-08-03 [project-rename-followup-local-folder](done/project-rename-followup-local-folder.md) - Re-confirmed rather than acted on: renaming the local checkout folder stays a manual step for the user, since this checkout is the live working tree for multiple concurrent sessions, exactly as project-rename's own Result already said (commit -)

- 2026-08-03 [settings-search-follow-up-4-confirmed](done/settings-search-follow-up-4-confirmed.md) - The "Yes works as intended" review text wasn't an exact match against the approval-word list, so it went through as a follow-up task per the strict-matching rule; checking it first showed nothing was actually needed, since the review itself already confirms the fix works (commit -)

- 2026-08-03 [settings-search-follow-up-4](done/settings-search-follow-up-4.md) - The settings search box kept dropping every keystroke after the first because an open Qt.WindowType.Popup steals the keyboard grab, so keys went to the popup instead of the focused line edit; the popup now forwards them back (Qt's own QCompleter pattern), with Escape closing it and Up/Down moving the highlighted row (commit -)

- 2026-08-03 [engine-still-not-closing](done/engine-still-not-closing.md) - Two gaps in MainWindow.closeEvent let gui.exe keep running after the main window closed: an already-deleted top-level widget could abort the closing sweep partway through, and the process still relied only on Qt's implicit quitOnLastWindowClosed bookkeeping rather than closeEvent quitting outright (commit -)

- 2026-08-03 [challenge-usage-option-label-cleanup](done/challenge-usage-option-label-cleanup.md) - Removed the redundant "Option" header label from the Today's Challenge Usage grid in gui/app/main_window.py; the three "Option 1/2/3" labels remain intact (commit -)

- 2026-08-03 [general-parentheses-tooltips-follow-up-3](done/general-parentheses-tooltips-follow-up-3.md) - Structural investigation, no code change: confirmed the local PyInstaller invocation matches CI byte-for-byte, actually built gui.exe locally and confirmed every Qt plugin the tooltip mechanism depends on is bundled correctly, and re-audited main.py/widgets.py for frozen-specific code paths, finding none. Closes as a documented investigation needing a live test from the user (commit -)

- 2026-08-03 [drop-legacy-release-exe-alias](done/drop-legacy-release-exe-alias.md) - release.yml no longer builds or publishes the second, pre-rename-named copy of the installer exe; each release now ships exactly one installer asset (Kimberlites-Macro-Menu.exe) plus update.ini (commit -)

- 2026-08-03 [multi-game-support](done/multi-game-support.md) - The macro supports multiple games, selectable from a new "Game" group on the General tab; each game has its own screens/presets/map placement/steps/timing settings, only disconnect support and the game-window settings stay shared. An existing config is migrated automatically into one default game on first launch (commit -)

- 2026-08-02 [project-rename](done/project-rename.md) - Renamed the project everywhere from "Kimberlite's Anime Expedition Macro" to "Kimberlite's Macro Menu": code, GUI, docs, the branded release exe, and the GitHub repository itself, with a one-hop legacy-name migration for existing installs and a temporary release-exe compatibility alias (commit -)

- 2026-08-02 [ocr-benchmark-autolaunch](done/ocr-benchmark-autolaunch.md) - Added EnsureOcrBenchmark() so the app auto-launches ocr_benchmark.exe if present, no separate program to run; re-cut as v0.4.16-dev2 (commit -)

- 2026-08-02 [benchmark-ocr-engines](done/benchmark-ocr-engines.md) - Built the live shadow-mode harness the user asked for instead of a written comparison: (commit -)

- 2026-08-02 [challenge-options-to-step-editor](done/challenge-options-to-step-editor.md) - The "Challenge options" group box (Option 1-3: Name/X/Y/Available at start/Priority/Max (commit -)

- 2026-08-02 [ci-automate-ocr-build](done/ci-automate-ocr-build.md) - added .github/workflows/ci.yml, triggered on push/pull_request to main, which installs (commit -)

- 2026-08-02 [coordinate-show-region-button](done/coordinate-show-region-button.md) - Added a "Show" point-preview button (a brief crosshair flash on screen, converted from (commit -)

- 2026-08-02 [decimal-separator-dot](done/decimal-separator-dot.md) - NoScrollDoubleSpinBox (gui/app/widgets.py), the single class every decimal spin box in the (commit -)

- 2026-08-02 [detailed-stats](done/detailed-stats.md) - Application Stats gains a Session Time cell; the AHK overlay's old plain-text "Screen Run (commit -)

- 2026-08-02 [dropdown-chevron-indicator-revert](done/dropdown-chevron-indicator-revert.md) - Reverted the drawComplexControl and _draw_combo_box_arrow methods entirely from CheckmarkProxyStyle in gui/app/widgets.py. The U+2304 chevron glyph override has been removed, restoring Qt Fusion's default QComboBox arrow rendering. All 247 GUI tests pass; checkbox drawing and other style features remain untouched. (commit -)

- 2026-08-02 [dropdown-chevron-indicator](done/dropdown-chevron-indicator.md) - Every QComboBox in the GUI now shows a wide/flat U+2304 (DOWN ARROWHEAD, "⌄") chevron instead (commit -)

- 2026-08-02 [general-parentheses-tooltips-follow-up-2](done/general-parentheses-tooltips-follow-up-2.md) - Re-investigated with new evidence rather than repeating the earlier stale-build conclusion (commit -)

- 2026-08-02 [general-parentheses-tooltips-follow-up](done/general-parentheses-tooltips-follow-up.md) - Investigated why the tooltips added by general-parentheses-to-tooltips (commit e15ddd4) (commit -)

- 2026-08-02 [keyboard-shortcuts-follow-up](done/keyboard-shortcuts-follow-up.md) - Replaced QMessageBox.question() with explicit QMessageBox instances configured with Icon.NoIcon in _delete_step and _delete_screen methods, removing the large question-mark icon from delete-confirmation dialogs while preserving text, buttons, and behavior. (commit -)

- 2026-08-02 [keyboard-shortcuts](done/keyboard-shortcuts.md) - Wired Delete/Backspace, Ctrl+D, Ctrl+N, F2 (and Ctrl+Up/Ctrl+Down for screens) as (commit -)

- 2026-08-02 [label-field-spacing-follow-up](done/label-field-spacing-follow-up.md) - Increased FORM_LAYOUT_HORIZONTAL_SPACING from 10px to 13px in gui/app/widgets.py, a 30% bump that is "just a bit" larger per user wording. All 247 GUI tests pass. (commit -)

- 2026-08-02 [label-field-spacing](done/label-field-spacing.md) - Added a `FormLayout` subclass in gui/app/widgets.py (setHorizontalSpacing(10), replacing (commit -)

- 2026-08-02 [map-placement-checkbox-order-follow-up-2](done/map-placement-checkbox-order-follow-up-2.md) - The General tab's Tower Loadout "click after each tower placed" checkbox now follows the label-first visual pattern applied in the earlier checkbox-order-follow-up task: the checkbox text moved into a QLabel with setBuddy() for accessibility, and the checkbox is now bare, matching the established pattern across the GUI. All GUI tests pass. (commit -)

- 2026-08-02 [map-placement-checkbox-order-follow-up](done/map-placement-checkbox-order-follow-up.md) - Swept gui/app/*.py for every QCheckBox placed before its own embedded label text inside a (commit -)

- 2026-08-02 [preset-settings-trim-fields](done/preset-settings-trim-fields.md) - Removed the Back X, Back Y, and Fallback screen rows/widgets from main_window.py's (commit -)

- 2026-08-02 [remove-challenge-option-basics](done/remove-challenge-option-basics.md) - Removed the "Challenge option basics" QGroupBox (Option 1-3 Name/X/Y/Available/Priority) (commit -)

- 2026-08-02 [remove-field-colons](done/remove-field-colons.md) - Every label-then-field form row across gui/app/*.py (QFormLayout.addRow calls and the (commit -)

- 2026-08-02 [rename-tab-presets](done/rename-tab-presets.md) - The main window's tab label (gui/app/main_window.py:275) now reads "Presets" instead of "Preset Settings"; the "Preset settings" QGroupBox inside that tab is unchanged. (commit -)

- 2026-08-02 [searchbar-placeholder-text](done/searchbar-placeholder-text.md) - The settings search box placeholder text (gui/app/main_window.py:239) now reads "Search..." instead of "Search settings...". (commit -)

- 2026-08-02 [selectable-gui-text](done/selectable-gui-text.md) - Every QLabel in the GUI (explicit and Qt-internal, e.g. via QFormLayout.addRow) is now (commit -)

- 2026-08-02 [settings-search-follow-up-2](done/settings-search-follow-up-2.md) - _settings_search_popup and its _settings_search_list now both set (commit -)

- 2026-08-02 [settings-search-follow-up-3](done/settings-search-follow-up-3.md) - Investigated whether the settings-search-follow-up-2 fix (commit c391e90, denies (commit -)

- 2026-08-01 [checkmarks](done/checkmarks.md) - Checked checkboxes now draw a real check-mark glyph (with a dash for (commit -)

- 2026-08-01 [engine-status-remove-fields](done/engine-status-remove-fields.md) - The top "Engine status" box in gui/app/main_window.py now shows only a minimal (commit -)

- 2026-08-01 [general-parentheses-to-tooltips](done/general-parentheses-to-tooltips.md) - Swept gui/app/*.py for static parenthetical label qualifiers and converted each to a (commit -)

- 2026-08-01 [map-placement-box-size](done/map-placement-box-size.md) - The Map Placement tab's tower-placement coordinates table now hides rows past the map's (commit -)

- 2026-08-01 [map-placement-checkbox-order](done/map-placement-checkbox-order.md) - Both checkboxes in the Map Placement tab's "Map placement settings" box now sit below the (commit -)

- 2026-08-01 [minimize-windows-independently](done/minimize-windows-independently.md) - All six secondary Qt windows (Edit Preset, Map Advanced Settings, Option Availability, (commit -)

- 2026-08-01 [preset-active-row-spacing](done/preset-active-row-spacing.md) - Added an 8px `addSpacing` gap between the preset list/buttons row and the "Runs on Start" / "Set as Active" row inside the Presets group box on the Preset Settings tab (gui/app/main_window.py, _build_preset_tab), so the two rows no longer sit flush against each other; the group box's outer border still encloses both rows unchanged. (commit -)

- 2026-08-01 [preset-widget-active-line-placement](done/preset-widget-active-line-placement.md) - the "Runs on Start" / "Set as Active" row now sits inside the Presets group box's own (commit -)

- 2026-08-01 [preset-widget-button-ellipsis](done/preset-widget-button-ellipsis.md) - The presets widget's "Edit...", "Export...", "Import..." buttons now read "Edit", "Export", (commit -)

- 2026-08-01 [python-owns-config](done/python-owns-config.md) - The Python GUI is now the single owner of config.ini, atomically and key-preserving; the AHK (commit -)

- 2026-08-01 [remote-agent-tab](done/remote-agent-tab.md) - Remote Agent Setup is now a permanent top-level tab (RemoteAgentTab, a QWidget in (commit -)

- 2026-08-01 [settings-search-follow-up](done/settings-search-follow-up.md) - The settings-search results popup (Qt.WindowType.Popup) implicitly grabbed keyboard focus (commit -)

- 2026-08-01 [settings-search](done/settings-search.md) - A "Search:" box (plain text label, no icon asset needed) sits top-right in the "Engine (commit -)

- 2026-08-01 [stats-reset](done/stats-reset.md) - StartMacro() now zeroes StartRepeatCount, VictoryCount and DefeatCount once per genuine new (commit -)

- 2026-08-01 [step-edit-window](done/step-edit-window.md) - The "Step Editor" group box moved out of Edit Preset into its own non-modal (commit -)

- 2026-08-01 [tower-loadout-first-slot-width](done/tower-loadout-first-slot-width.md) - In the General tab's "Tower Loadout" QGridLayout (gui/app/main_window.py), the "Number of (commit -)

- 2026-07-31 [autoupdate-startup-broken](done/autoupdate-startup-broken.md) - gui.exe now offers, downloads, verifies (sha256) and installs a newer release on startup via (commit -)

- 2026-07-31 [config-load-failure-permanent](done/config-load-failure-permanent.md) - "Every General field 0" is exactly the GeneralConfig() dataclass default set, i.e. the (commit -)

- 2026-07-31 [config-read-race-on-save](done/config-read-race-on-save.md) - ConfigChangeTracker.changed() (gui/ipc/client.py) used to report a config.ini change to (commit -)

- 2026-07-31 [default-map-dropdown](done/default-map-dropdown.md) - preset_default_map, preset_fallback_screen, and the ten general_slot_N combos on the (commit -)

- 2026-07-31 [engine-survives-close-followup](done/engine-survives-close-followup.md) - main_window.closeEvent now closes every visible top-level widget instead of only the (commit -)

- 2026-07-31 [engine-survives-close](done/engine-survives-close.md) - Closing the main window now stops the AutoHotkey engine in both cases that used to leave (commit -)

- 2026-07-31 [escape-blocks-other-apps](done/escape-blocks-other-apps.md) - Escape:: is now guarded by a #HotIf predicate (EscapeHasSomethingToCancel) that only (commit -)

- 2026-07-31 [local-bridge-stuck-command](done/local-bridge-stuck-command.md) - local_cmd.txt older than 90s (past PAIR_REMOTE_AGENT's ~50s worst case) is now treated as (commit -)

- 2026-07-31 [pin-one-shot-move](done/pin-one-shot-move.md) - Follow-up from escape-blocks-other-apps: Pin (F7 / the Pin button) now calls (commit -)

- 2026-07-31 [pin-rename](done/pin-rename.md) - F7 / the Pin button / the local bridge's FORCE_GAME_WINDOW command now only move and lock (commit -)

- 2026-07-31 [refresh-game-processes-stuck-busy](done/refresh-game-processes-stuck-busy.md) - Two independent fixes, both confirmed by static reading (live repro still not authorized (commit -)

- 2026-07-31 [release-staging-list](done/release-staging-list.md) - Two hand-maintained files stage a finished change through two rounds of testing before a (commit -)

- 2026-07-31 [steps-table](done/steps-table.md) - The step order view in Edit Preset is now a QTableWidget with one column per field (Type, (commit -)

- 2026-07-31 [tower-loadout-slot-choices](done/tower-loadout-slot-choices.md) - The Tower Loadout dropdowns (General tab) were populated from _all_option_names(), i.e. the (commit -)

- 2026-07-31 [unhandled-error-1934-flash](done/unhandled-error-1934-flash.md) - LoadGeneralSlots(), LoadMapProfile() and LoadPreset() in macro/tower_defense_macro_gui.ahk (commit -)

- 2026-07-31 [website-header-rebrand](done/website-header-rebrand.md) - Renamed the site's top-left/brand text in remote/server/web/index.html to "Kimberlite's (commit -)

- 2026-07-30 [codex-sol-to-terra](done/codex-sol-to-terra.md) - CLAUDE.md "Codex delegation" now uses gpt-5.6-terra for complex logic and tells Claude to (commit -)

- 2026-07-30 [preset-edit-scroll](done/preset-edit-scroll.md) - gui/app/edit_preset_window.py wraps the editor in a QScrollArea with setWidgetResizable(True), (commit -)
