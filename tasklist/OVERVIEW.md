AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead
(see "Tasklist routine" in CLAUDE.md). A stale OVERVIEW.md next to accurate task files is not a
conflict worth resolving by hand, just regenerate it.

Last regenerated: 2026-08-03 (after completing challenge-usage-option-label-cleanup)

## FIXES

1. [engine-still-not-closing](open/fixes/engine-still-not-closing.md) - Follow-up from engine-survives-close-followup: the user tried the merged fix (closeEvent       sweeping every visible top-level widget instead of only the three tracked collections) and
       it still does not close the engine/process correctly. Find out why the sweep is not enough
       and fix the actual remaining leak, instead of the level this was already fixed at once.

## WORKFLOW

(none open)

## GUI & UX

1. [screen-detection-settings-placement](open/gui-ux/screen-detection-settings-placement.md) - The "Screen Detection" group box in the preset/screen editor       (gui/app/edit_preset_window.py, currently always shown, ~lines 115-138) is no longer always
       visible; it moves under/inside a "Screen Settings" section that is only shown when the user
       wants to see or edit detection, decluttering the default step-editing view. Resolved shape:
       a "Screen Settings..." button opening a dedicated dialog window; default view shows just the
       step list.

2. [settings-search-follow-up-4](open/gui-ux/settings-search-follow-up-4.md) - Follow-up from settings-search-follow-up-3: the settings search box still stops accepting       keystrokes and the user's original reproduction steps still hold, even though the
       settings-search-follow-up-2 NoFocus fix (c391e90) is verified sound on current main by a
       full passing test suite. Explicitly deprioritized by the user: postpone this if no obvious
       fix surfaces quickly, it is stealing too much focus right now relative to its impact.

## MAJOR

1. [detailed-stats-follow-up](open/major/detailed-stats-follow-up.md) - Follow-up from detailed-stats: remove the Time Breakdown overlay's Step Time table, show the       currently active step's accumulative time inside the Application Stats panel instead, and
       grow the Screen Time table to fill the space the removed Step Time table leaves.

2. [screen-detection-overhaul](open/major/screen-detection-overhaul.md) - A screen is self-identifying: it starts with its own entry detection, then runs its steps,       then the global screen detection decides which screen comes next. Ties are resolved by a
       per-screen configured default instead of by step order.

3. [global-screens](open/major/global-screens.md) - Screens (their name, identity and entry detection, per [[screen-detection-overhaul]]) are       defined once globally instead of being duplicated inside every preset's
       `[Preset_<name>]` section. Every preset recognizes the same set of screens; only the
       step-sequence run on each screen stays preset-specific. The "Challenges" preset's current
       3 screens (Before Map Detection / Ingame / Round End) are the template for the migration:
       they become the global screen set every other preset is migrated onto.

4. [ocr-expected-variants](open/major/ocr-expected-variants.md) - Any "expected text" field used for OCR matching supports several independent text variants       instead of a single string, each checked separately (exact match first, then the existing
       6-character fuzzy fallback) so any one matching variant counts as detected. Wherever a "Test
       OCR" button already exists for such a field, a new button next to it (working label "Add as
       expected") adds the just-recognized text as a new variant.

5. [private-server-link](open/major/private-server-link.md) - A private server link is stored once in the settings; after a disconnect the macro rejoins       through that link instead of the normal public rejoin. Empty field = today's behavior.

6. [remote-agent-tab-online-settings](open/major/remote-agent-tab-online-settings.md) - The "Remote Agent" tab (gui/app/remote_agent_tab.py) is renamed to "Online Settings", drops       its explanatory text, and is trimmed down to just sign-in and pair; the agent executable path
       field is replaced by automatic detection instead of manual entry, and the server URL is fixed
       to kimberlitemacro.duckdns.org instead of being user-entered. Explicitly deprioritized by the
       user: not needed right now, kept for later.

7. [rapidfuzz-fuzzy-matching](open/major/rapidfuzz-fuzzy-matching.md) - OCR expected-text comparisons (`TextContainsPartialMatch` in tower_defense_macro_gui.ahk,       currently a fixed-length substring-window heuristic) use a real edit-distance/similarity
       score instead, so match quality no longer depends on a hardcoded window size.

8. [opencv-template-matching](open/major/opencv-template-matching.md) - Screens and steps can be detected by OpenCV template or color matching, as an alternative to       the existing OCR-text detection, for cases text recognition handles poorly (icons, color
       states, non-text UI elements).

9. [agent-self-update-codesigning](open/major/agent-self-update-codesigning.md) - animeexpedition-agent.exe updates itself automatically (reading AGENT_LATEST_VERSION from the       backend) instead of requiring the operator to distribute updates manually, without triggering
       Windows SmartScreen/user-trust warnings.

## DONE (newest first)

- 2026-08-03 [multi-game-support](done/multi-game-support.md)
- 2026-08-03 [general-parentheses-tooltips-follow-up-3](done/general-parentheses-tooltips-follow-up-3.md)
- 2026-08-03 [drop-legacy-release-exe-alias](done/drop-legacy-release-exe-alias.md)
- 2026-08-03 [challenge-usage-option-label-cleanup](done/challenge-usage-option-label-cleanup.md)
- 2026-08-02 [settings-search-follow-up-3](done/settings-search-follow-up-3.md)
- 2026-08-02 [settings-search-follow-up-2](done/settings-search-follow-up-2.md)
- 2026-08-02 [selectable-gui-text](done/selectable-gui-text.md)
- 2026-08-02 [searchbar-placeholder-text](done/searchbar-placeholder-text.md)
- 2026-08-02 [rename-tab-presets](done/rename-tab-presets.md)
- 2026-08-02 [remove-field-colons](done/remove-field-colons.md)
- 2026-08-02 [remove-challenge-option-basics](done/remove-challenge-option-basics.md)
- 2026-08-02 [project-rename](done/project-rename.md)
- 2026-08-02 [preset-settings-trim-fields](done/preset-settings-trim-fields.md)
- 2026-08-02 [ocr-benchmark-autolaunch](done/ocr-benchmark-autolaunch.md)
- 2026-08-02 [map-placement-checkbox-order-follow-up-2](done/map-placement-checkbox-order-follow-up-2.md)
- 2026-08-02 [map-placement-checkbox-order-follow-up](done/map-placement-checkbox-order-follow-up.md)
- 2026-08-02 [label-field-spacing-follow-up](done/label-field-spacing-follow-up.md)
- 2026-08-02 [label-field-spacing](done/label-field-spacing.md)
- 2026-08-02 [keyboard-shortcuts-follow-up](done/keyboard-shortcuts-follow-up.md)
- 2026-08-02 [keyboard-shortcuts](done/keyboard-shortcuts.md)
- 2026-08-02 [general-parentheses-tooltips-follow-up-2](done/general-parentheses-tooltips-follow-up-2.md)
- 2026-08-02 [general-parentheses-tooltips-follow-up](done/general-parentheses-tooltips-follow-up.md)
- 2026-08-02 [dropdown-chevron-indicator-revert](done/dropdown-chevron-indicator-revert.md)
- 2026-08-02 [dropdown-chevron-indicator](done/dropdown-chevron-indicator.md)
- 2026-08-02 [detailed-stats](done/detailed-stats.md)
- 2026-08-02 [decimal-separator-dot](done/decimal-separator-dot.md)
- 2026-08-02 [coordinate-show-region-button](done/coordinate-show-region-button.md)
- 2026-08-02 [ci-automate-ocr-build](done/ci-automate-ocr-build.md)
- 2026-08-02 [challenge-options-to-step-editor](done/challenge-options-to-step-editor.md)
- 2026-08-02 [benchmark-ocr-engines](done/benchmark-ocr-engines.md)
- 2026-08-01 [tower-loadout-first-slot-width](done/tower-loadout-first-slot-width.md)
- 2026-08-01 [step-edit-window](done/step-edit-window.md)
- 2026-08-01 [stats-reset](done/stats-reset.md)
- 2026-08-01 [settings-search-follow-up](done/settings-search-follow-up.md)
- 2026-08-01 [settings-search](done/settings-search.md)
- 2026-08-01 [remote-agent-tab](done/remote-agent-tab.md)
- 2026-08-01 [python-owns-config](done/python-owns-config.md)
- 2026-08-01 [preset-widget-button-ellipsis](done/preset-widget-button-ellipsis.md)
- 2026-08-01 [preset-widget-active-line-placement](done/preset-widget-active-line-placement.md)
- 2026-08-01 [preset-active-row-spacing](done/preset-active-row-spacing.md)
- 2026-08-01 [minimize-windows-independently](done/minimize-windows-independently.md)
- 2026-08-01 [map-placement-checkbox-order](done/map-placement-checkbox-order.md)
- 2026-08-01 [map-placement-box-size](done/map-placement-box-size.md)
- 2026-08-01 [general-parentheses-to-tooltips](done/general-parentheses-to-tooltips.md)
- 2026-08-01 [engine-status-remove-fields](done/engine-status-remove-fields.md)
- 2026-08-01 [checkmarks](done/checkmarks.md)
- 2026-07-31 [website-header-rebrand](done/website-header-rebrand.md)
- 2026-07-31 [unhandled-error-1934-flash](done/unhandled-error-1934-flash.md)
- 2026-07-31 [tower-loadout-slot-choices](done/tower-loadout-slot-choices.md)
- 2026-07-31 [steps-table](done/steps-table.md)
- 2026-07-31 [release-staging-list](done/release-staging-list.md)
- 2026-07-31 [refresh-game-processes-stuck-busy](done/refresh-game-processes-stuck-busy.md)
- 2026-07-31 [pin-rename](done/pin-rename.md)
- 2026-07-31 [pin-one-shot-move](done/pin-one-shot-move.md)
- 2026-07-31 [local-bridge-stuck-command](done/local-bridge-stuck-command.md)
- 2026-07-31 [escape-blocks-other-apps](done/escape-blocks-other-apps.md)
- 2026-07-31 [engine-survives-close-followup](done/engine-survives-close-followup.md)
- 2026-07-31 [engine-survives-close](done/engine-survives-close.md)
- 2026-07-31 [default-map-dropdown](done/default-map-dropdown.md)
- 2026-07-31 [config-read-race-on-save](done/config-read-race-on-save.md)
- 2026-07-31 [config-load-failure-permanent](done/config-load-failure-permanent.md)
- 2026-07-31 [autoupdate-startup-broken](done/autoupdate-startup-broken.md)
- 2026-07-30 [preset-edit-scroll](done/preset-edit-scroll.md)
- 2026-07-30 [codex-sol-to-terra](done/codex-sol-to-terra.md)