Title: Placement mode soll auf pin umbenannt werden, und das window nur noch auf die position
pinnen. Die gui mit log und status die normalerweise beim macroen stehen sollen nicht mehr
auftauchen. Der pin button ist lediglich das window an die richtige stelle zu bekommen um positions
festzulegen.
noch dazu nur das window soll pinned sein aber der rest der grau hintergrund alles logs soll nicht
da sein
Prio:  5

Goal:  F7 only pins the game window into the opening rectangle so positions can be captured. Nothing
       else appears: no status/log window, and no gray fullscreen overlay either, only the game
       window itself gets moved/resized. The feature is called "Pin" everywhere.
Files: gui/app/main_window.py, gui/app/capture.py, macro/tower_defense_macro_gui.ahk (F7 hotkey,
       PlacementModeClick, ForceGameWindow, CreateOverlay, EnforceWindowLock)
Steps: 1. Rename "Placement mode" to "Pin" in GUI text, tooltips, hotkey hints and log messages.
       2. In the pin path (PlacementModeClick -> ForceGameWindow), skip CreateOverlay() entirely:
          today it always creates both the 4 gray overlay bar windows and the log/status GUI, and
          both must stay off while pinning. Keep only the window-find/restore/activate/move logic
          (MoveWindowToVisibleRect) and the EnforceWindowLock timer that keeps it in place.
       3. Check that F8 capture still works while pinned and that Escape still cancels.
       4. Update the Documentation tab in remote/server/web/index.html where placement mode is
          described.
Open:  Does the pin toggle (stays until pressed again) or release itself when capturing ends?
