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

## GUI & UX

- settings-search-follow-up-2 - the settings search results popup and its list no longer accept
  keyboard focus at all, so typing into the search box no longer stops registering once the
  results popup is showing (the earlier fix only reclaimed focus once, right after the popup's
  first show())

  Review:


- map-placement-checkbox-order-follow-up - the Map Placement tab's two checkboxes, plus every other
  genuine checkbox-before-text occurrence found in a sweep (Disconnect Detection's reconnect
  checkbox, the Step Editor's fallback/advanced checkboxes), now show their label text first and the
  checkbox second, inline with the other label-then-field rows

  Review:


- general-parentheses-tooltips-follow-up - investigated the "I don't see the tooltips" report;
  verified the tooltip code from general-parentheses-to-tooltips is correct (no gui/ file changed),
  the real cause was that no release had shipped that commit yet, so the installed app was still on
  the old pre-tooltip build. Added a CLAUDE.md note so a future session checks release ancestry
  before treating a similar confusing review as a bug.

  Review:


- challenge-options-to-step-editor - the "Challenge options" widget (Option 1-3 Name/X/Y/Available/
  Priority/Max uses/Availability Check) moved out of Edit Preset's always-visible layout into the
  Step Editor window, shown only for "Option Select" steps; the Availability Check button moved with
  it, and the options still share one set of data across the whole preset

  Review:


- keyboard-shortcuts - the steps table and screens list in Edit Preset now react to Delete/
  Backspace (delete selected, now always confirms), Ctrl+D (duplicate, steps only), Ctrl+N (add),
  F2 (rename screens / edit steps), and Ctrl+Up/Ctrl+Down (move screens); each shortcut only
  fires while that exact widget has focus, so it never steals Backspace from a text field elsewhere
  in the dialog

  Review:


- searchbar-placeholder-text - the settings search box placeholder text now reads "Search..."
  instead of "Search settings..."

  Review:


- rename-tab-presets - the main window's "Preset Settings" tab label now reads "Presets"; the
  "Preset settings" group box inside that tab is unchanged

  Review:


- preset-settings-trim-fields - the "Preset settings" group box on the Presets tab now shows only
  "Default map:"; Back X, Back Y, and Fallback screen were removed from it since Edit Preset already
  has its own fully independent editor for those same three fields, which remains the place to set
  them

  Review:


- remove-challenge-option-basics - the "Challenge option basics" group box (Option 1-3 Name/X/Y/
  Available/Priority) was removed from the Presets tab; the Step Editor's "Challenge options" widget
  (from challenge-options-to-step-editor) is now the only editor for that data, and "Today's
  Challenge Usage" directly below is unaffected, still reading the same preset.options data

  Review:


- remove-field-colons - every label-then-field form row across gui/app/*.py (QFormLayout.addRow and
  the equivalent _add_editor_row/_add_row helpers) now shows its label without a trailing colon;
  standalone/status labels like "Search:" and "Runs on Start: -" are unchanged, they were out of
  scope

  Review:


- decimal-separator-dot - NoScrollDoubleSpinBox (gui/app/widgets.py), the single class every
  decimal field in the GUI is built from, now sets its own C locale so it always displays and
  parses a period decimal separator regardless of the system locale (was rendering "12,500" under
  German Windows); AHK's SafeInt/SafeNum and config.ini's storage format are untouched, this is
  display-only

  Review:


- label-field-spacing - the horizontal gap between a field's label and its input widget is now
  10px instead of Qt's 6px default, everywhere the QFormLayout label-then-field pattern occurs
  (main_window.py, edit_preset_window.py, step_edit_window.py, map_advanced_window.py,
  option_availability_window.py, advanced_outcomes_window.py, remote_agent_tab.py), via a single
  shared FormLayout subclass

  Review:


- dropdown-chevron-indicator - every QComboBox dropdown arrow now shows a wide, flat U+2304 chevron
  ("⌄") instead of Fusion's pointy default triangle, via a drawComplexControl override on the
  existing CheckmarkProxyStyle (gui/app/widgets.py), applied app-wide, so it covers every combo box
  automatically with no per-widget or style.qss change

  Review:


- selectable-gui-text - every QLabel in the app (explicit ones and the ones Qt creates internally,
  e.g. via QFormLayout.addRow) is now mouse-selectable/copyable via a polish() override on the
  existing CheckmarkProxyStyle (gui/app/widgets.py), applied app-wide with no per-call-site changes;
  QGroupBox title text is not a QLabel and has no text-interaction API, so it stays out of scope

  Review:


- coordinate-show-region-button - added a "Show" point-preview button (a brief crosshair flash on
  screen, using the same AHK-side percent-to-pixel conversion as the OCR "Show Region" button) next
  to every X/Y coordinate field: Map Placement's per-slot placements_table rows, Edit Preset's
  Back X/Y, and in the Step Editor both step_x/step_y and step_end_x/step_end_y plus each Challenge
  option's X/Y

  Review:

## MAJOR

- detailed-stats - Application Stats gains a Session Time cell; the AHK overlay's old plain-text
  "Screen Run Counts" box is replaced with ListView tables of per-screen/per-step time; all three
  reset on every restart; the same stats reach the remote website live plus as persisted session
  history (new dashboard sections)

  Review: