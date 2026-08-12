Title: Remove the widget in presets "todays challenge usage" and every other time the mechanic is
       used in the program.
Prio:  2

Goal:  The daily challenge-usage mechanic is gone from the whole program, not just from the Preset
       Settings tab. That means the "Today's Challenge Usage" group box
       (gui/app/main_window.py:578, its Used / Daily limit spin boxes at :584-:595, _usage_changed
       at :1364 and the load path at :1054-:1055), the per-option counters it edits, and the engine
       logic that consumes them.

       The mechanic reaches further than the widget, which is why this sits in major rather than
       gui-ux. Known touch points to work through:
       - macro/tower_defense_macro_gui.ahk: the refresh helper at :1143-:1150 and UsageBoxControls
         at :1325 (the AHK-side copy of the same group), and the option-selection logic at
         :4871-:4905, which reads Option<N>MaxUses and GetOptionUsedToday() to decide whether an
         option may still be used today. Removing the counters means deciding what that selection
         does instead.
       - Config keys: Option<N>MaxUses plus the used-today counters, read by
         gui/ipc/config_reader.py:320 and written by gui/ipc/config_writer.py (:875-:898,
         set_option_used_count / the max-uses writer, and the two option-template dicts at :648 and
         :950 that seed "maxUses": 0).
       - The bridge protocol: gui/ipc/protocol.py:264 carries "maxUses", so the wire type, both
         sides of it and its tests move together.
       This continues a dismantling the backlog already started: done/remove-challenge-option-basics,
       done/challenge-options-to-step-editor and done/challenge-usage-option-label-cleanup each took
       a piece of the same mechanic.

Open:  - What happens to option selection once max-uses is gone? Today an option that hit its daily
         limit is skipped. Removing the limit silently changes which option a running preset picks,
         so the replacement behavior (always eligible? priority only?) is a decision the user has to
         make, not one to infer from the removal request.
       - Whether the Option<N>MaxUses keys should be actively deleted from existing config.ini
         files or just stop being read. Leaving them costs nothing and is reversible; deleting them
         is tidier but destroys the numbers if the user ever wants the mechanic back.
       - Whether "Priority" and the Option Availability check stay. They sit next to max-uses in the
         same option record but are separate mechanics, and the request names only usage.
