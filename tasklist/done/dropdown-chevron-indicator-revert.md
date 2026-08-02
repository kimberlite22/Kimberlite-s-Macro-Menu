Title:     well i dont see it but honestly its fine remove youre changes from this task and then put it
           to done
Completed: 2026-08-02
Commit:    -

Result: Reverted the drawComplexControl and _draw_combo_box_arrow methods entirely from CheckmarkProxyStyle in gui/app/widgets.py. The U+2304 chevron glyph override has been removed, restoring Qt Fusion's default QComboBox arrow rendering. All 247 GUI tests pass; checkbox drawing and other style features remain untouched.
