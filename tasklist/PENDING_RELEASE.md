HAND-MAINTAINED. Never regenerated. See "Pending release lists" in CLAUDE.md.

Changes the user already approved once in PENDING_REVIEW.md, staged here for one more check right
before a release ships them. One line per change with a blank line between consecutive entries,
grouped by task group in the fixed order fixes, workflow, gui-ux, major:

    - [ ] <slug> - <one-liner>

Check a line off (`- [x]`) once it has been retested for the release. Once every entry is checked,
clear the file down to this header: the explanatory text above and the template line above stay,
every pending entry and now-empty group heading is removed.

## FIXES

- [ ] tower-loadout-first-slot-width - the first tower loadout slot field in the General tab is now
  the same width as the other nine, instead of noticeably wider

## GUI & UX

- [ ] stats-reset - victory/defeat and all lifetime stats counters now reset on every genuine new
  Start (F10 or the Qt GUI's Start button), but not on an internal restart (disconnect
  auto-reconnect or a queued preset switch), which continues the same session.

- [ ] map-placement-box-size - the tower placement coordinates box on the Map Placement tab now
  shrinks or grows to fit exactly the selected number of slots, and both the box and the Capture
  button are narrower.

- [ ] step-edit-window - the Step Editor moved out of Edit Preset into its own non-modal window,
  opened via double-click / "Edit Step..." / "Add Step"; it has its own Save/Cancel and reuses one
  instance across rows.

- [ ] minimize-windows-independently - Edit Preset, Map Advanced Settings, Option Availability,
  Advanced Outcomes, Remote Agent Setup, and the Step Editor no longer minimize/hide together with
  the main window (or vice versa); each can be minimized and restored independently now.

- [ ] remote-agent-tab - Remote Agent Setup is now a permanent top-level tab instead of a separate
  window opened from the bottom strip, and the "Enable remote bridge" checkbox moved into it too.

- [ ] checkmarks - checked checkboxes now show a real check-mark glyph (a dash when partially
  checked) instead of a filled square, everywhere in the GUI, including hover and disabled states.

- [ ] engine-status-remove-fields - the top "Engine status" box now shows only a minimal
  Idle/Running/Paused label; the removed detail line (active/running/queued preset, map, screen,
  step) and counters line (cycles, step repeats, start repeats, victories, defeats) are gone.

- [ ] preset-widget-button-ellipsis - the presets widget's "Edit...", "Export...", "Import..."
  buttons no longer show a trailing "...".

- [ ] preset-active-row-spacing - a small gap now separates the preset list/buttons row from the
  "Runs on Start" / "Set as Active" row inside the Presets group box.

- [ ] challenge-options-to-step-editor - the "Challenge options" widget (Option 1-3 Name/X/Y/
  Available/Priority/Max uses/Availability Check) moved out of Edit Preset's always-visible layout
  into the Step Editor window, shown only for "Option Select" steps; the Availability Check button
  moved with it, and the options still share one set of data across the whole preset.

- [ ] searchbar-placeholder-text - the settings search box placeholder text now reads "Search..."
  instead of "Search settings...".

- [ ] rename-tab-presets - the main window's "Preset Settings" tab label now reads "Presets"; the
  "Preset settings" group box inside that tab is unchanged.

- [ ] preset-settings-trim-fields - the "Preset settings" group box on the Presets tab now shows
  only "Default map:"; Back X, Back Y, and Fallback screen were removed from it since Edit Preset
  already has its own fully independent editor for those same three fields.

- [ ] remove-challenge-option-basics - the "Challenge option basics" group box (Option 1-3 Name/X/Y/
  Available/Priority) was removed from the Presets tab; the Step Editor's "Challenge options" widget
  is now the only editor for that data, and "Today's Challenge Usage" is unaffected.

- [ ] remove-field-colons - every label-then-field form row across gui/app/*.py now shows its label
  without a trailing colon; standalone/status labels like "Search:" and "Runs on Start: -" are
  unchanged, they were out of scope.

- [ ] decimal-separator-dot - NoScrollDoubleSpinBox, the single class every decimal field in the GUI
  is built from, now sets its own C locale so it always displays and parses a period decimal
  separator regardless of the system locale (was rendering "12,500" under German Windows).

- [ ] selectable-gui-text - every QLabel in the app (explicit ones and the ones Qt creates
  internally) is now mouse-selectable/copyable via a polish() override on the existing
  CheckmarkProxyStyle, applied app-wide; QGroupBox title text stays out of scope.

- [ ] coordinate-show-region-button - added a "Show" point-preview button (a brief crosshair flash
  on screen) next to every X/Y coordinate field: Map Placement's per-slot placements_table rows,
  Edit Preset's Back X/Y, and in the Step Editor both step_x/step_y and step_end_x/step_end_y plus
  each Challenge option's X/Y.
