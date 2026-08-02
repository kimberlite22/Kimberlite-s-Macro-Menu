AUTO-GENERATED. Do not hand-edit: regenerate from tasklist/open/ and tasklist/done/ instead
(see "Tasklist routine" in CLAUDE.md). A stale OVERVIEW.md next to accurate task files is not a
conflict worth resolving by hand, just regenerate it.

Last regenerated: 2026-08-02

## FIXES

1. [engine-still-not-closing](open/fixes/engine-still-not-closing.md) - follow-up from
   engine-survives-close-followup: the merged fix still does not close the engine/process
   correctly. Postponed to a later release at the user's request.

## GUI & UX

1. [screen-detection-settings-placement](open/gui-ux/screen-detection-settings-placement.md) -
   screen detection settings move under a Screen Settings section instead of always showing.
   BLOCKED: its target group box no longer exists after a revert; needs
   screen-detection-overhaul re-decided first.

2. [selectable-gui-text](open/gui-ux/selectable-gui-text.md) - GUI text labels become
   selectable/copyable with the mouse.

3. [coordinate-show-region-button](open/gui-ux/coordinate-show-region-button.md) - X/Y coordinate
   fields get a button that briefly shows that location on screen, like the OCR "Show region"
   button.

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

6. [remote-agent-tab-online-settings](open/major/remote-agent-tab-online-settings.md) - Remote
   Agent tab reworked into a trimmed-down "Online Settings" tab with auto-detected agent path and
   a fixed server URL. Reclassified from gui-ux and postponed at the user's request; not needed
   right now.

## DONE (newest first)

- 2026-08-02 [dropdown-chevron-indicator](done/dropdown-chevron-indicator.md) - every QComboBox
  dropdown arrow now shows a wide, flat U+2304 chevron ("⌄") instead of Fusion's pointy default
  triangle, via a drawComplexControl override on the existing CheckmarkProxyStyle
  (gui/app/widgets.py), applied app-wide (commit -)

- 2026-08-02 [label-field-spacing](done/label-field-spacing.md) - the horizontal gap between a
  field's label and its input widget is now 10px instead of Qt's 6px default, everywhere the
  QFormLayout label-then-field pattern occurs, via a single shared FormLayout subclass
  (commit -)

- 2026-08-02 [decimal-separator-dot](done/decimal-separator-dot.md) - NoScrollDoubleSpinBox
  (gui/app/widgets.py), the single class every decimal field in the GUI is built through, now sets
  its own C locale so it always displays and parses a period decimal separator regardless of the
  system locale (was rendering "12,500" under German Windows); AHK's SafeInt/SafeNum and
  config.ini's storage format untouched, display-only (commit -)

- 2026-08-02 [remove-field-colons](done/remove-field-colons.md) - every label-then-field form row
  across gui/app/*.py (QFormLayout.addRow calls and the equivalent _add_editor_row/_add_row
  helpers, plus the manually built label-then-field rows in main_window.py) no longer has a
  trailing colon; standalone/status labels ("Search:", "Runs on Start: -", "Agent: ...") were left
  untouched, out of scope (commit -)

- 2026-08-02 [remove-challenge-option-basics](done/remove-challenge-option-basics.md) - removed the
  "Challenge option basics" group box (Option 1-3 Name/X/Y/Available/Priority) from the Presets tab;
  the Step Editor's "Challenge options" widget (from challenge-options-to-step-editor) is now the
  sole editor for that data, "Today's Challenge Usage" unaffected (commit -)

- 2026-08-02 [preset-settings-trim-fields](done/preset-settings-trim-fields.md) - the "Preset
  settings" group box on the Presets tab now shows only Default map; Back X, Back Y, and Fallback
  screen were removed from it, staying editable in Edit Preset's own already-existing editor for
  those three fields (commit 23e39fb)

- 2026-08-02 [rename-tab-presets](done/rename-tab-presets.md) - the main window's "Preset Settings"
  tab label now reads "Presets"; the "Preset settings" group box inside that tab is unchanged
  (commit -)

- 2026-08-02 [searchbar-placeholder-text](done/searchbar-placeholder-text.md) - the settings search
  box placeholder text now reads "Search..." instead of "Search settings..." (commit -)

- 2026-08-02 [keyboard-shortcuts](done/keyboard-shortcuts.md) - the steps table and screens list in
  Edit Preset now react to Delete/Backspace (delete selected, now always confirms), Ctrl+D
  (duplicate, steps only), Ctrl+N (add), F2 (rename screens / edit steps), and Ctrl+Up/Ctrl+Down
  (move screens), each shortcut scoped to fire only while that exact widget has focus (commit -)

- 2026-08-02 [detailed-stats](done/detailed-stats.md) - Application Stats gains a Session Time cell;
  the AHK overlay's old plain-text "Screen Run Counts" box is replaced with ListView tables of
  per-screen/per-step time; all three reset on every restart; the same stats reach the remote
  website live plus as persisted session history (new dashboard sections) (commit -)

- 2026-08-02 [challenge-options-to-step-editor](done/challenge-options-to-step-editor.md) - the
  "Challenge options" widget (Option 1-3 Name/X/Y/Available/Priority/Max uses/Availability Check)
  moved out of Edit Preset's always-visible layout into the Step Editor, shown only for "Option
  Select" steps; the Availability Check button moved with it, and the data stayed shared per-preset
  (commit -)

- 2026-08-02 [general-parentheses-tooltips-follow-up](done/general-parentheses-tooltips-follow-up.md)
  - investigated the "I don't see the tooltips" review comment; the tooltip code from
  general-parentheses-to-tooltips is correct (verified with a headless PySide6 probe, no gui/ file
  changed), the real cause was that no release had shipped that commit yet so the installed app was
  still on the pre-tooltip build; added a CLAUDE.md note to check release ancestry before treating a
  similar review as a bug (commit bd476e1)

- 2026-08-02 [map-placement-checkbox-order-follow-up](done/map-placement-checkbox-order-follow-up.md)
  - five genuine checkbox-before-text occurrences (Map Placement's two checkboxes, Disconnect
  Detection's reconnect checkbox, and the Step Editor's fallback/advanced checkboxes) now show
  their label text first and a bare checkbox second, inline with the other label-then-field rows
  (commit -)

- 2026-08-02 [settings-search-follow-up-2](done/settings-search-follow-up-2.md) - the settings
  search results popup and its list now both refuse keyboard focus outright
  (Qt.FocusPolicy.NoFocus), so typing into the search box no longer stops registering once the
  popup is showing (the earlier fix only reclaimed focus once, right after the popup's first
  show())

- 2026-08-01 [map-placement-checkbox-order](done/map-placement-checkbox-order.md) - both Map
  Placement tab checkboxes now sit below the "Number of placements" field with a small gap, order
  unchanged (custom tower slots, then custom camera actions) (commit -)

- 2026-08-01 [settings-search-follow-up](done/settings-search-follow-up.md) - fixed the
  settings-search results popup implicitly stealing keyboard focus from the search box on every
  keystroke, and removed the temporary #f0c674 highlight flash when navigating to a search result
  (destination still gets focus and the tab/window switch) (commit -)

- 2026-08-01 [preset-active-row-spacing](done/preset-active-row-spacing.md) - added an 8px gap
  between the preset list/buttons row and the "Runs on Start" / "Set as Active" row inside the
  Presets group box on the Preset Settings tab (commit -)

- 2026-08-01 [settings-search](done/settings-search.md) - a "Search:" box top-right of the main
  window (next to "Engine status") finds a setting by name across the three main tabs, the Remote
  Agent tab, the bottom action buttons, and the Edit Preset/Map Advanced/Option
  Availability/Step Editor/Advanced Outcomes windows, showing a results list and jumping to/
  highlighting the chosen field; no new icon asset, a plain "Search:" text label (commit -)

- 2026-08-01 [general-parentheses-to-tooltips](done/general-parentheses-to-tooltips.md) -
  parenthetical qualifiers on static GUI labels (units, "0 = unlimited", checkbox clarifications, a
  group box title, table column headers) are now hover tooltips instead of inline parenthesized
  text, across the General tab, Preset tab, Map Advanced Settings, Step Editor, and Option
  Availability Check (commit -)

- 2026-08-01 [preset-widget-button-ellipsis](done/preset-widget-button-ellipsis.md) - the presets
  widget's "Edit...", "Export...", "Import..." left-side buttons now read "Edit", "Export",
  "Import" (commit -)

- 2026-08-01 [preset-widget-active-line-placement](done/preset-widget-active-line-placement.md) -
  the "Runs on Start" / "Set as Active" row now sits inside the Presets group box's own bordered
  outline, below the preset list and its buttons, instead of below the box as a separate row
  (commit -)

- 2026-08-01 [tower-loadout-first-slot-width](done/tower-loadout-first-slot-width.md) - the first
  tower loadout slot field in the General tab is now the same width as the other nine (commit -)

- 2026-08-01 [engine-status-remove-fields](done/engine-status-remove-fields.md) - the top "Engine
  status" box now shows only a minimal Idle/Running/Paused label; the removed detail line (active/
  running/queued preset, map, screen, step) and counters line (cycles, step repeats, start repeats,
  victories, defeats) are gone from this strip, without touching the underlying LocalStatus/
  local_status.json fields other consumers still read (commit e97fcdb)

- 2026-08-01 [checkmarks](done/checkmarks.md) - checked checkboxes now draw a real check-mark glyph
  (a dash for tristate) instead of a filled square, via a CheckmarkProxyStyle covering hover/
  disabled states and any future checkable list/table item too (commit 7ccfa67)

- 2026-08-01 [remote-agent-tab](done/remote-agent-tab.md) - Remote Agent Setup is now a permanent
  top-level tab (RemoteAgentTab) instead of a QDialog opened from a bottom-strip button; the
  "Enable remote bridge" checkbox moved into it too (commit -)

- 2026-08-01 [minimize-windows-independently](done/minimize-windows-independently.md) - Edit
  Preset, Map Advanced Settings, Option Availability, Advanced Outcomes, Remote Agent Setup, and
  the Step Editor no longer minimize/hide together with the main window in either direction; each
  can be minimized and restored on its own (commit -)

- 2026-08-01 [step-edit-window](done/step-edit-window.md) - the Step Editor moved out of Edit
  Preset into its own non-modal window, opened via double-click / "Edit Step..." / "Add Step",
  with its own Save/Cancel and one reused instance per row click (commit -)

- 2026-08-01 [map-placement-box-size](done/map-placement-box-size.md) - the Map Placement tab's
  tower placement coordinates box now resizes vertically to fit exactly the selected number of
  slots, and both the box and the Capture button are narrower (commit -)

- 2026-08-01 [stats-reset](done/stats-reset.md) - StartMacro() zeroes the lifetime Start Repeat/
  Victory/Defeat counters once per genuine new Start, but not on an internal restart (disconnect
  auto-reconnect, queued preset switch), which continues the same session (commit a3d35e3)

- 2026-08-01 [python-owns-config](done/python-owns-config.md) - the Python GUI is now the single
  owner of config.ini, writing it itself atomically and key-preserving; the AHK engine is read-only
  except for the one-time coordinate migration and two small accepted exceptions. The hidden native
  AHK editor GUI (~3400 lines) is deleted outright (commit -)

- 2026-07-31 [engine-survives-close-followup](done/engine-survives-close-followup.md) - closing
  the GUI now closes every visible top-level window instead of only the three directly-tracked
  collections, so a window nested inside another (Edit Preset's Option Availability picker) can no
  longer keep gui.exe running in the background (commit -)

- 2026-07-31 [config-load-failure-permanent](done/config-load-failure-permanent.md) - a failed
  FIRST config.ini read no longer strands the window on all-zero placeholders forever (it retries
  until one read lands), and Save is refused in that state instead of writing the placeholders
  over an intact config (commit -)

- 2026-07-31 [tower-loadout-slot-choices](done/tower-loadout-slot-choices.md) - the General tab's
  Tower Loadout dropdowns now offer the engine's own hotbar positions 1-6 instead of the preset's
  challenge option names, so a saved slot no longer looks unset (no data was lost) (commit -)

- 2026-07-31 [config-read-race-on-save](done/config-read-race-on-save.md) - the background config
  poll now waits for config.ini's mtime to settle across two consecutive polls before re-reading
  it, instead of reacting to the first sign of movement mid-save-burst and occasionally losing the
  resulting sharing-violation race ("config.ini could not be read", errno 13) (commit -)

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
