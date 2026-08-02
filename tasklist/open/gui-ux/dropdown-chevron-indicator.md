Title: Mach bei allen dropdown menüs sichtbar das sie dropdown menüs sind durch einen symbol ⌄ sowas
       aber mehr breiter und nicht so pointy gibt es auch oft in anderen apps.
Prio:  15

Goal:  Every QComboBox / dropdown in the GUI (NoScrollComboBox and plain QComboBox instances across
       gui/app/*.py, styled via gui/app/style.qss) shows a clear, wide/flat chevron-style dropdown
       indicator instead of the current arrow, so it reads as a dropdown at a glance, similar to the
       flatter chevron style common in other apps.
Open:  Exact chevron glyph/asset and size are a visual judgment call; needs a look at the current
       style.qss QComboBox::down-arrow rule and a decision on whether it becomes a Unicode glyph, a
       drawn shape, or a small SVG/PNG asset.
