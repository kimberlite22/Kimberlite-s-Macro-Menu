Title: ok but increase the space between the line and the box with presets a litte bit
Prio:  1

Goal:  Follow-up from preset-widget-active-line-placement: add a small visible gap between the
       preset list/buttons row and the "Runs on Start" / "Set as Active" row inside the Presets
       group box on the Preset Settings tab, since the two rows currently sit flush against each
       other.
Files: gui/app/main_window.py (_build_preset_tab, ~lines 422-456)
Steps: 1. In _build_preset_tab (gui/app/main_window.py), between
          `selector_box_layout.addLayout(selector_layout)` (~line 445) and
          `selector_box_layout.addLayout(active_layout)` (~line 455), insert
          `selector_box_layout.addSpacing(<N>)` with a small value (e.g. 8-10px) so the "Runs on
          Start" / "Set as Active" row reads as visibly separated from the preset list/buttons row
          above it, matching "a little bit" rather than a large gap.
       2. Confirm the Presets group box's own outer border still fully encloses both rows unchanged
          (only the inter-row spacing changes, not the box itself), preserving what
          preset-widget-active-line-placement already established.
Open:  -
