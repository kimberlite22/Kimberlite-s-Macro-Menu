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
