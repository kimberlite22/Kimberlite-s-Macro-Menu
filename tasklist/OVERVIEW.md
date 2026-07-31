AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead
(see "Tasklist routine" in CLAUDE.md). A stale OVERVIEW.md next to accurate task files is not a
conflict worth resolving by hand, just regenerate it.

Last regenerated: 2026-07-31

## FIXES

1. [engine-survives-close](open/fixes/engine-survives-close.md) - closing the GUI always also stops
   the hidden engine process.
2. [tower-loadout-first-slot-width](open/fixes/tower-loadout-first-slot-width.md) - first tower
   loadout slot in General matches the width of the other slots.

## GUI & UX

1. [stats-reset](open/gui-ux/stats-reset.md) - reset victory/defeat and all stats when the macro
   (re)starts.
2. [map-placement-box-size](open/gui-ux/map-placement-box-size.md) - the tower placement coordinates
   box resizes to fit the selected slots, box and capture button both narrower.
3. [remote-agent-tab](open/gui-ux/remote-agent-tab.md) - Remote agent setup as its own top-level
   tab.
4. [checkmarks](open/gui-ux/checkmarks.md) - checked checkboxes show a real check glyph.
5. [minimize-windows-independently](open/gui-ux/minimize-windows-independently.md) - minimizing one
   app window no longer minimizes the other.
6. [screen-detection-settings-placement](open/gui-ux/screen-detection-settings-placement.md) -
   screen detection settings move under a Screen Settings section instead of always showing.
7. [engine-status-remove-fields](open/gui-ux/engine-status-remove-fields.md) - remove running/
   queued/map/screen/step/cycles/repeats/victories/defeats from the top engine status strip.
8. [preset-widget-active-line-placement](open/gui-ux/preset-widget-active-line-placement.md) - move
   the "runs on start / set as active" line inside the presets widget's bordered box.
9. [preset-widget-button-ellipsis](open/gui-ux/preset-widget-button-ellipsis.md) - remove the
   trailing "..." from the presets widget's left-side buttons.
10. [general-parentheses-to-tooltips](open/gui-ux/general-parentheses-to-tooltips.md) - turn
    parenthetical descriptions into hover tooltips.
11. [settings-search](open/gui-ux/settings-search.md) - a top-right search box to find a setting.

## MAJOR

1. [private-server-link](open/major/private-server-link.md) - paste a private server link to
   auto-rejoin it on disconnect.
2. [project-rename](open/major/project-rename.md) - rename the project from Kimberlite's Anime
   Expedition Macro to Kimberlite's Macro Menu everywhere.
3. [multi-game-support](open/major/multi-game-support.md) - support multiple games with separate
   configs, screens and map placement, sharing only disconnect support and the game window.
4. [detailed-stats](open/major/detailed-stats.md) - add session time / per-screen time / per-step
   time to the stats, on the website too, and redesign the running-GUI's stats box.

## DONE (newest first)

- 2026-07-31 [escape-blocks-other-apps](done/escape-blocks-other-apps.md) - Escape only intercepts
  the key while there is something to cancel/stop, instead of swallowing it system-wide at all times
  (commit -)
- 2026-07-31 [release-staging-list](done/release-staging-list.md) - PENDING_REVIEW.md /
  PENDING_RELEASE.md two-stage testing between "merged" and "release" (commit -)
- 2026-07-31 [global-screens](done/global-screens.md) - screen entry-detection criteria can be
  shared by name across presets via a new global registry, opt-in per preset-screen (commit -)
- 2026-07-31 [steps-table](done/steps-table.md) - step order shown as a real table instead of
  |-separated text (commit dc63830)
- 2026-07-31 [pin-rename](done/pin-rename.md) - Placement mode renamed to Pin; pinning now shows no
  gray overlay, log or stats panel, only the game window itself moves (commit 816fb5f)
- 2026-07-31 [default-map-dropdown](done/default-map-dropdown.md) - preset default map, preset
  fallback screen, and the ten general slot pickers are now select-only dropdowns instead of
  editable free text (commit -)
- 2026-07-31 [website-header-rebrand](done/website-header-rebrand.md) - live site's top-left
  branding renamed to Kimberlite's Macro Menu (commit c227556)
- 2026-07-31 [screen-detection-overhaul](done/screen-detection-overhaul.md) - self-identifying
  screen entry detection with global fallback/conflict resolution (commit 9af9a4f)
- 2026-07-31 [autoupdate-startup-broken](done/autoupdate-startup-broken.md) - self-updating startup
  flow (commit 0c9c655)
- 2026-07-30 [preset-edit-scroll](done/preset-edit-scroll.md) - Edit Preset window scrolls
  (commit 2993000)
- 2026-07-30 [codex-sol-to-terra](done/codex-sol-to-terra.md) - Codex delegation moved to terra
  (commit 99766b1)
