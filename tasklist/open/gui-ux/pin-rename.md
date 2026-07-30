Title: Placement mode soll auf pin umbenannt werden, und das window nur noch auf die position
pinnen. Die gui mit log und status die normalerweise beim macroen stehen sollen nicht mehr
auftauchen. Der pin button ist lediglich das window an die richtige stelle zu bekommen um positions
festzulegen.
Prio:  1

Goal:  F7 only pins the game window into the opening rectangle so positions can be captured. No
       status/log overlay appears, and the feature is called "Pin" everywhere.
Files: gui/app/main_window.py, gui/app/capture.py, macro/tower_defense_macro_gui.ahk (F7 hotkey,
       placement mode, overlay / window lock)
Steps: 1. Rename "Placement mode" to "Pin" in GUI text, tooltips, hotkey hints and log messages.
       2. Strip the status/log overlay out of the pin path, leaving only the window move/resize
          into the opening rectangle.
       3. Check that F8 capture still works while pinned and that Escape still cancels.
       4. Update the Documentation tab in remote/server/web/index.html where placement mode is
          described.
Open:  Does the pin toggle (stays until pressed again) or release itself when capturing ends?
