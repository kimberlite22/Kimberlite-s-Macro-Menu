Title: Victory und defeat count und generell alle stats sollen beim neustarten des macros resettet
werden
Prio:  2

Goal:  Starting the macro shows counters from zero. A previous session's victory/defeat numbers
       never bleed into the new run.
Files: macro/tower_defense_macro_gui.ahk (StartMacro, the counter globals, the remote_status.json
       writer), the stats display in gui/app/main_window.py
Steps: 1. Collect the counter globals and reset them inside StartMacro's Critical block, next to
          the existing per-session flag reset.
       2. Make sure internal restarts (disconnect auto-reconnect, queued preset switch) do NOT
          reset, since they continue the same session.
       3. Push the zeroed values into remote_status.json and the GUI so the display clears at once.
Open:  Does "Neustart des Macros" mean restarting the app, or every press of Start? Should a
       queued preset switch count as a new session (new preset, fresh stats) or not?
