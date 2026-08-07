Title: Ausserdem soll roblox automatisch fullscreen sein nicht mehr in der alten bilschiratio weil
       wir den platz fuer die ui ja nicht mehr brauchen. Die ui soll dann in die pyhton gui aber das
       koennen wir auch spaeter verschieben.

Prio:  3

Goal:  From the same INBOX note as roblox-join-without-browser: the game window is pinned to the full
       screen instead of the smaller opening rectangle the old layout used. The opening
       (General / Game Window tab: Opening offset X/Y, Opening width/height, stored as
       [General] HoleX/HoleY/HoleW/HoleH and used by ForceGameWindow) was sized to leave room next to
       the game for the AHK GUI; the shipped app now runs that GUI as a separate Qt window, so that
       space is no longer needed and Roblox should come up filling the screen. The user notes that
       moving the remaining UI into the Python GUI is a separate, later step, so this task is about
       the window geometry only.

Open:  Decisions to settle first:
       - Coordinates are stored as percent-of-opening (see "Key conventions" in CLAUDE.md), so
         changing the opening changes what every existing preset's percentages point at. Decide
         whether existing configs are migrated, left alone with the old opening, or whether the
         change only applies to newly created presets; a silent reframe would break every saved
         position.
       - Whether "fullscreen" means the opening is set to the primary display's full bounds (the
         macro keeps driving a normal window, which keeps pinning and the overlay working) or Roblox
         itself is put into its own fullscreen mode. The second one is the riskier reading: it
         changes how the game window can be found, moved and locked at all.
       - Whether this should follow the display the background session actually runs on rather than
         the local primary display, since the background session already resolves its own resolution
         (done/background-session-match-desktop-resolution.md).
