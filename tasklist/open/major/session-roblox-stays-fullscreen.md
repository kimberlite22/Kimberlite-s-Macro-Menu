Title: Roblox soll in der session in full screen starten und auch bleiben fuer immer. Das macro soll
       nicht resizen wenn es in der session gestartet wird

Prio:  2

Goal:  In a background session the game window is full screen from the moment it appears and stays
       that way, and the macro stops moving or resizing it there at all. Today the window is put
       where it belongs after the fact: ForceGameWindow moves it into the opening and
       EnforceWindowLock snaps it back twice a second (tower_defense_macro_gui.ahk). In a session
       that exists only to run the game that is work with no purpose, since the opening IS the
       session's whole screen (see done/roblox-fullscreen-opening.md), and it is also visible: the
       window appears at whatever size Roblox chose and is then resized. After this task the engine
       recognises that it runs in a background session (InBackgroundWindowsSession already exists
       and is resolved once at startup, see done/background-session-hide-engine-overlay.md) and
       leaves the geometry alone, while Roblox comes up full screen by itself and cannot be pushed
       out of it.

Open:  What actually makes Roblox come up full screen has to be settled first, and it decides how
       much of this task there is:
       - Roblox remembers its own window size per Windows user, so a session that shares the
         physical desktop's profile inherits whatever size was last used there. Whether that is
         enough (set it once, it sticks) or whether the engine has to assert it on every start is
         the central question, and it is answered by trying it, not by reading.
       - If it has to be asserted: is that the borderless-full-screen window this repo already
         builds (done/roblox-fullscreen-opening.md strips WS_CAPTION and sizes the window to the
         screen), or Roblox' own fullscreen mode? The first one is a move/resize, which is exactly
         what this task says to stop doing in a session, so "not resizing" and "forcing full screen"
         have to be reconciled rather than both taken literally.
       - Whether "stays for ever" needs anything watching it at all. Dropping EnforceWindowLock in a
         session removes the only thing that would put the window back if something moved it; decide
         whether that risk is real in a session with no user in front of it.
       - Whether the pin hotkey and the local bridge's FORCE_GAME_WINDOW verb should also become
         no-ops in a session, or keep working as a manual override.
