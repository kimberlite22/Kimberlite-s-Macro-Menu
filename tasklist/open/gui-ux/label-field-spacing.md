Title: Bei preset settings vergrößere den minimum space zwischen text und feldern ein wenig nicht
       viel aber so sagen wird 1.5x mach das bei allen vorkommen dieses musters.
Prio:  14

Goal:  The horizontal gap between a field's label text and its input widget (the QFormLayout
       label-to-field spacing pattern used throughout the Preset Settings tab and, per this request,
       everywhere else the same pattern occurs) is increased to roughly 1.5x its current minimum -
       a small but visible bump, not a large one.
Open:  "This pattern" spans QFormLayout usages across gui/app/main_window.py,
       edit_preset_window.py, step_edit_window.py, map_advanced_window.py,
       option_availability_window.py, advanced_outcomes_window.py, remote_agent_tab.py; confirm a
       single global QFormLayout spacing/style tweak is intended rather than per-window adjustments.
