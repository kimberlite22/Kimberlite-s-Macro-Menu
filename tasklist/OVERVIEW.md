AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead
(see "Tasklist routine" in CLAUDE.md). A stale OVERVIEW.md next to accurate task files is not a
conflict worth resolving by hand, just regenerate it.

Last regenerated: 2026-07-31

## FIXES

1. [tower-loadout-first-slot-width](open/fixes/tower-loadout-first-slot-width.md) - first tower
   loadout slot in General matches the width of the other slots.

## GUI & UX

1. [stats-reset](open/gui-ux/stats-reset.md) - reset victory/defeat and all stats when the macro
   (re)starts.
2. [map-placement-box-size](open/gui-ux/map-placement-box-size.md) - the tower placement coordinates
   box resizes to fit the selected slots, box and capture button both narrower.
3. [minimize-windows-independently](open/gui-ux/minimize-windows-independently.md) - minimizing one
   app window no longer minimizes the other.
4. [remote-agent-tab](open/gui-ux/remote-agent-tab.md) - Remote agent setup as its own top-level
   tab.
5. [screen-detection-settings-placement](open/gui-ux/screen-detection-settings-placement.md) -
   screen detection settings move under a Screen Settings section instead of always showing.
6. [checkmarks](open/gui-ux/checkmarks.md) - checked checkboxes show a real check glyph.
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

1. [screen-detection-overhaul](open/major/screen-detection-overhaul.md) - a screen becomes
   self-identifying: its own entry detection, then its steps, then global screen detection picks
   the next screen, ties resolved by a per-screen default. Unmerged from main for the 0.4.x fix
   release; to be redone later.
2. [global-screens](open/major/global-screens.md) - screen name/identity/entry-detection defined
   once globally instead of duplicated per preset, seeded from the Challenges preset. Depends on
   [[screen-detection-overhaul]]; unmerged from main for the 0.4.x fix release; to be redone later.
3. [private-server-link](open/major/private-server-link.md) - paste a private server link to
   auto-rejoin it on disconnect.
4. [project-rename](open/major/project-rename.md) - rename the project from Kimberlite's Anime
   Expedition Macro to Kimberlite's Macro Menu everywhere.
5. [multi-game-support](open/major/multi-game-support.md) - support multiple games with separate
   configs, screens and map placement, sharing only disconnect support and the game window.
6. [detailed-stats](open/major/detailed-stats.md) - add session time / per-screen time / per-step
   time to the stats, on the website too, and redesign the running-GUI's stats box.

## DONE (newest first)

- 2026-07-31 [refresh-game-processes-stuck-busy](done/refresh-game-processes-stuck-busy.md) - the
  local IPC client detects an unresponsive AHK engine from its own heartbeat instead of a flat
  90s guess, clearing a stuck local_cmd.txt in a few seconds; the Refresh button also disables
  itself while its command is in flight so a reentrant click cannot queue a duplicate (commit -)
- 2026-07-31 [unhandled-error-1934-flash](done/unhandled-error-1934-flash.md) - the DropDownList
  fields for Option Priority / General slots / placement counts now fall back safely on stale
  config data through SetDdlTextSafe() instead of throwing "Invalid value" at every engine launch
  (commit -)
- 2026-07-31 [local-bridge-stuck-command](done/local-bridge-stuck-command.md) - a stale
  local_cmd.txt older than 90s is now cleared instead of blocking every future command forever;
  config.ini reads retry past a transient sharing violation; the GUI keeps the last known-good
  config on a later transient read failure instead of blanking it to defaults (commit -)
- 2026-07-31 [engine-survives-close](done/engine-survives-close.md) - closing the GUI now also
  stops an engine it only attached to, and closes open secondary windows so the process actually
  quits (commit -)
- 2026-07-31 [pin-one-shot-move](done/pin-one-shot-move.md) - follow-up from
  escape-blocks-other-apps: Pin moves the game window into place once and leaves it alone, no
  ongoing lock, so being pinned no longer claims the Escape key (commit -)
- 2026-07-31 [escape-blocks-other-apps](done/escape-blocks-other-apps.md) - Escape only intercepts
  the key while there is something to cancel/stop, instead of swallowing it system-wide at all times
  (commit -)
- 2026-07-31 [release-staging-list](done/release-staging-list.md) - PENDING_REVIEW.md /
  PENDING_RELEASE.md two-stage testing between "merged" and "release" (commit -)
- 2026-07-31 [steps-table](done/steps-table.md) - step order shown as a real table instead of
  |-separated text (commit dc63830)
- 2026-07-31 [pin-rename](done/pin-rename.md) - Placement mode renamed to Pin; pinning now shows no
  gray overlay, log or stats panel, only the game window itself moves (commit 816fb5f)
- 2026-07-31 [default-map-dropdown](done/default-map-dropdown.md) - preset default map, preset
  fallback screen, and the ten general slot pickers are now select-only dropdowns instead of
  editable free text (commit -)
- 2026-07-31 [website-header-rebrand](done/website-header-rebrand.md) - live site's top-left
  branding renamed to Kimberlite's Macro Menu (commit c227556)
- 2026-07-31 [autoupdate-startup-broken](done/autoupdate-startup-broken.md) - self-updating startup
  flow (commit 0c9c655)
- 2026-07-30 [preset-edit-scroll](done/preset-edit-scroll.md) - Edit Preset window scrolls
  (commit 2993000)
- 2026-07-30 [codex-sol-to-terra](done/codex-sol-to-terra.md) - Codex delegation moved to terra
  (commit 99766b1)
