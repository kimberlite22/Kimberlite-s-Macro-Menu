Title:     Bei preset settings vergrößere den minimum space zwischen text und feldern ein wenig
           nicht viel aber so sagen wird 1.5x mach das bei allen vorkommen dieses musters.
Completed: 2026-08-02
Commit:    -

Result: Added a `FormLayout` subclass in gui/app/widgets.py (setHorizontalSpacing(10), replacing
Qt's default of 6px) and replaced every raw QFormLayout(...) construction with it across
main_window.py, edit_preset_window.py, step_edit_window.py, map_advanced_window.py,
option_availability_window.py, advanced_outcomes_window.py, and remote_agent_tab.py - a single
global choke point, per the user's confirmed decision, rather than per-window tweaks. 6px to 10px
is close to the requested "roughly 1.5x, a small bump" (~1.67x).
