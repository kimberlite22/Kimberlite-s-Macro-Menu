HAND-MAINTAINED. Never regenerated. See "Pending release lists" in CLAUDE.md.

Changes a Claude session just finished, staged here so the user can try them once before they move
to PENDING_RELEASE.md for the final pre-release check. Two lines per change, grouped by task group in
the fixed order fixes, workflow, gui-ux, major:

    - <slug> - <one-liner>
      Review:

Fill in the Review: line yourself once you have tried the change, right here in the file, no chat
needed: a bare approval word and nothing else (approved / ok / okay / yes / lgtm) means it works, no
follow-up needed. Anything else, including an approval word plus more text ("approved, but X" does
NOT count), is read as a follow-up change to make in full, your own words, no particular format
required. The next /tasklist run resolves it: an approval moves the entry to PENDING_RELEASE.md, a
follow-up becomes a new task under tasklist/open/ (this line's text is its Title) and this entry is
dropped.

## FIXES

- tower-loadout-first-slot-width - the first tower loadout slot field in the General tab is now the
  same width as the other nine, instead of noticeably wider
  Review:

## GUI & UX

- stats-reset - victory/defeat and all lifetime stats counters now reset on every genuine new Start
  (F10 or the Qt GUI's Start button), but not on an internal restart (disconnect auto-reconnect or a
  queued preset switch), which continues the same session.
  Review:
- map-placement-box-size - the tower placement coordinates box on the Map Placement tab now shrinks
  or grows to fit exactly the selected number of slots, and both the box and the Capture button are
  narrower.
  Review:
- step-edit-window - the Step Editor moved out of Edit Preset into its own non-modal window,
  opened via double-click / "Edit Step..." / "Add Step"; it has its own Save/Cancel and reuses one
  instance across rows.
  Review:
- minimize-windows-independently - Edit Preset, Map Advanced Settings, Option Availability,
  Advanced Outcomes, Remote Agent Setup, and the Step Editor no longer minimize/hide together with
  the main window (or vice versa); each can be minimized and restored independently now.
  Review:
- remote-agent-tab - Remote Agent Setup is now a permanent top-level tab instead of a separate
  window opened from the bottom strip, and the "Enable remote bridge" checkbox moved into it too.
  Review:
- checkmarks - checked checkboxes now show a real check-mark glyph (a dash when partially checked)
  instead of a filled square, everywhere in the GUI, including hover and disabled states.
  Review:
- engine-status-remove-fields - the top "Engine status" box now shows only a minimal
  Idle/Running/Paused label; the removed detail line (active/running/queued preset, map, screen,
  step) and counters line (cycles, step repeats, start repeats, victories, defeats) are gone.
  Review:
