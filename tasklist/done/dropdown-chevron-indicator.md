Title:     Mach bei allen dropdown menüs sichtbar das sie dropdown menüs sind durch einen symbol ⌄ sowas
           aber mehr breiter und nicht so pointy gibt es auch oft in anderen apps.
Completed: 2026-08-02
Commit:    -

Result: Every QComboBox in the GUI now shows a wide/flat U+2304 (DOWN ARROWHEAD, "⌄") chevron instead
of Fusion's pointy default triangle, via a drawComplexControl override added to the existing
CheckmarkProxyStyle (gui/app/widgets.py), which is already applied app-wide. Pure QSS was ruled out:
Qt's stylesheet url() for QComboBox::down-arrow only resolves qrc/file paths, never data: URIs
(verified empirically), so a Unicode glyph there without a new asset file needed the same proxy-style
mechanism the codebase already uses for checkbox glyphs.
