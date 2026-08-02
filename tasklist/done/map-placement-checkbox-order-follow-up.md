Title:     Reverse die order also zuerst der text dann die checkmark damit es inline mti den anderen
           feldern im widget ist. Mach das auch bei anderen vorkommen gleicher muster.
Completed: 2026-08-02
Commit:    -

Result: Swept gui/app/*.py for every QCheckBox placed before its own embedded label text inside a
label+field row (a blank QFormLayout/grid label paired with a checkbox that carries its own text) and
reordered all five genuine occurrences to text-first-then-checkbox, moving each checkbox's text into
its row's own label (with a trailing colon to match sibling rows) and leaving a bare `QCheckBox()` as
the field widget: `map_custom_towers` and `map_custom_camera` in the Map Placement tab's "Map
placement settings" box, `general_disconnect_enabled` in the General tab's "Disconnect Detection" box,
and `step_fallback_enabled` / `step_advanced` in the Step Editor window (all in
gui/app/main_window.py and gui/app/step_edit_window.py). Also added `field_label.setBuddy(widget)` to
step_edit_window.py's `_add_editor_row` helper (found by the auto-review) since the two now-bare
checkboxes there had lost their accessible name once their text moved into a manually built QLabel
that never associated itself as the widget's buddy (QFormLayout.addRow(str, widget) does this
automatically, so the main_window.py rows were unaffected). Left standalone checkboxes/radios that
carry their own inline text with no adjacent blank-label row to align to untouched: map_advanced_window
.py's `custom_camera`, main_window.py's `general_after_place_click` and `preset_option_available`,
option_availability_window.py's `invert_checkbox`, remote_agent_tab.py's
`remote_bridge_enabled_checkbox`, step_edit_window.py's `step_once`, and the login/register
QRadioButtons in remote_agent_tab.py.
