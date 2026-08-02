AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead
(see "Tasklist routine" in CLAUDE.md). A stale OVERVIEW.md next to accurate task files is not a
conflict worth resolving by hand, just regenerate it.

Last regenerated: 2026-08-02 (after label-field-spacing-follow-up)

## FIXES

1. [engine-still-not-closing](open/fixes/engine-still-not-closing.md) - Follow-up from engine-survives-close-followup: the user tried the merged fix (cl
   oseEvent
       sweeping every visible top-level widget instead of only the three tracked collections) and
       it still does not close the engine/process correctly. Find out why the sweep is not enough
       and fix the actual remaining leak, instead of the level this was already fixed at once.

## WORKFLOW

(none open)

## GUI & UX

1. [screen-detection-settings-placement](open/gui-ux/screen-detection-settings-placement.md) - The "Screen Detection" group box in the preset/screen editor
       (gui/app/edi
   t_preset_window.py, currently always shown, ~lines 115-138) is no longer always
       visible; it moves under/inside a "Screen Settings" section that is only shown when the user
       wants to see or edit detection, decluttering the default step-editing view. Resolved shape:
       a "Screen Settings..." button opening a dedicated dialog window; default view shows just the
       step list.

## MAJOR

1. [detailed-stats-follow-up](open/major/detailed-stats-follow-up.md) - Follow-up from detailed-stats: remove the Time Breakdown overlay's Step Time tab
   le, show the
       currently active step's accumulative time inside the Application Stats panel instead, and
       grow the Screen Time table to fill the space the removed Step Time table leaves.
2. [screen-detection-overhaul](open/major/screen-detection-overhaul.md) - A screen is self-identifying: it starts with its own entry detection, then runs 
   its steps,
       then the global screen detection decides which screen comes next. Ties are resolved by a
       per-screen configured default instead of by step order.
3. [global-screens](open/major/global-screens.md) - Screens (their name, identity and entry detection, per [[screen-detection-overha
   ul]]) are
       defined once globally instead of being duplicated inside every preset's
       `[Preset_<name>]` section. Every preset recognizes the same set of screens; only the
       step-sequence run on each screen stays preset-specific. The "Challenges" preset's current
       3 screens (Before Map Detection / Ingame / Round End) are the template for the migration:
       they become the global screen set every other preset is migrated onto.
4. [ocr-expected-variants](open/major/ocr-expected-variants.md) - Any "expected text" field used for OCR matching supports several independent tex
   t variants
       instead of a single string, each checked separately (exact match first, then the existing
       6-character fuzzy fallback) so any one matching variant counts as detected. Wherever a "Test
       OCR" button already exists for such a field, a new button next to it (working label "Add as
       expected") adds the just-recognized text as a new variant.
5. [private-server-link](open/major/private-server-link.md) - A private server link is stored once in the settings; after a disconnect the mac
   ro rejoins
       through that link instead of the normal public rejoin. Empty field = today's behavior.
6. [project-rename](open/major/project-rename.md) - Every occurrence of the project's old name ("Anime Expedition macro" / "Kimberli
   te's Anime
       Expedition Macro") in the codebase, GUI, docs and public-facing surfaces reads "Kimberlite's
       Macro Menu" instead.
7. [multi-game-support](open/major/multi-game-support.md) - The macro supports multiple different games, selectable from a setting in Genera
   l. Each game
       has its own separate config (screens, map placement, presets, steps, etc.) except disconnect
       support and the game-window settings, which stay shared across every game. Screens are
       entirely game-specific; only some components are game-specific (which ones is left to a
       later, more detailed note from the user).
8. [remote-agent-tab-online-settings](open/major/remote-agent-tab-online-settings.md) - The "Remote Agent" tab (gui/app/remote_agent_tab.py) is renamed to "Online Setti
   ngs", drops
       its explanatory text, and is trimmed down to just sign-in and pair; the agent executable path
       field is replaced by automatic detection instead of manual entry, and the server URL is fixed
       to kimberlitemacro.duckdns.org instead of being user-entered. Explicitly deprioritized by the
       user: not needed right now, kept for later.
9. [rapidfuzz-fuzzy-matching](open/major/rapidfuzz-fuzzy-matching.md) - OCR expected-text comparisons (`TextContainsPartialMatch` in tower_defense_macro
   _gui.ahk,
       currently a fixed-length substring-window heuristic) use a real edit-distance/similarity
       score instead, so match quality no longer depends on a hardcoded window size.
10. [opencv-template-matching](open/major/opencv-template-matching.md) - Screens and steps can be detected by OpenCV template or color matching, as an al
   ternative to
       the existing OCR-text detection, for cases text recognition handles poorly (icons, color
       states, non-text UI elements).
11. [agent-self-update-codesigning](open/major/agent-self-update-codesigning.md) - animeexpedition-agent.exe updates itself automatically (reading AGENT_LATEST_VER
   SION from the
       backend) instead of requiring the operator to distribute updates manually, without triggering
       Windows SmartScreen/user-trust warnings.

## DONE (newest first)

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
