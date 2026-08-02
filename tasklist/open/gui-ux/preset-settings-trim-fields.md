Title: In presets remove im  widget preset settings die felder, back x back y und fallback screen
       lass nur default map
Prio:  10

Goal:  The "Preset settings" group box on the Preset Settings tab (gui/app/main_window.py:465-476)
       keeps only the "Default map:" row; the "Back X", "Back Y", and "Fallback screen" rows are
       removed from the widget.
Open:  Back X/Y and Fallback screen are still real preset config fields read elsewhere (e.g.
       disconnect/reconnect logic); confirm whether removing their editor here means they become
       fixed/defaulted values, or whether they need to remain settable somewhere else instead of
       simply losing their only editor.
