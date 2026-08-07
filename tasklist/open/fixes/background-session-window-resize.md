Title: Mach auch das man das window der remote verbindung auch normal resizen kann, weil im moment
       ist das so das man nur abschneidet und der inhalt der remote session ist aber immer noch
       fullscreen, also in 100% bildschimr nimmt es ein. Wenn ich das window resize dann schneidet
       es nur den teil ab es wird aber nicht kleiner wie es sein soll eigentlich.
Prio:  2

Goal:  Resizing the Show window of the background session scales its content instead of cropping
       it. Follow-up on background-session-launcher: the .rdp file it writes pins a fixed
       1024x768 desktop with no scaling at all, which is exactly the reported behavior.
Files: gui/app/background_session.py (_rdp_file_lines), gui/tests/test_background_session.py
Steps: 1. Add "smart sizing:i:1" to the .rdp settings, so the client scales the session picture
          into whatever window size the user picks.
       2. Deliberately do NOT use "dynamic resolution:i:1", even though it is the crisper option.
          It changes the session's real resolution as the window is dragged, and this macro pins
          the game window into a fixed "opening" rectangle whose coordinates are all stored as a
          percentage of it (see "Key conventions" in CLAUDE.md). A resolution change under a
          running macro moves that reference frame and silently breaks every stored coordinate,
          which is far worse than a slightly soft preview image. Record this reasoning in a
          comment so a later change does not "upgrade" it back.
       3. Cover it in the .rdp file test alongside the existing prompt-suppression assertions.
Open:  -
