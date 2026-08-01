Title:     Jeder checkmark soll auch ein checkmark sein nicht einfach nur ein ausgefüllter kasten
Completed: 2026-08-01
Commit:    7ccfa67

Result: Checked checkboxes now draw a real check-mark glyph (with a dash for
tristate) instead of a filled square, via a new CheckmarkProxyStyle in
gui/app/widgets.py that also covers hover/disabled states and, by overriding
both PE_IndicatorCheckBox and PE_IndicatorItemViewItemCheck, any future
checkable list/table item too.
