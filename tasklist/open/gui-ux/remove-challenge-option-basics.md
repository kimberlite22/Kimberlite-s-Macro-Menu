Title: In preset settings, remove das widget Challenge option basics
       Remove bei presets die challenge option basics
Prio:  11

Goal:  The "Challenge option basics" group box on the Preset Settings tab
       (gui/app/main_window.py:479-511, Option 1-3 Name/X/Y/Available/Priority) is removed entirely
       from the tab layout. This is a different widget from the "Challenge options" group box in the
       Edit Preset window (gui/app/edit_preset_window.py:134, target of
       challenge-options-to-step-editor), which is unaffected by this task.
Open:  The preset_option_names/x/y/available/priority fields back real config data also read by the
       "Today's Challenge Usage" box directly below and by step logic elsewhere; confirm whether that
       data can lose its editor here outright, or needs to stay editable somewhere else (e.g. still
       reachable via the Edit Preset window's own "Challenge options" box) before deleting the
       fields.
