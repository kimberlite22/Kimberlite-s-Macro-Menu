Title: Die ingame macro gui mit grauen hintergrund und so weiter verschwindet komplett (nur wenn man
       über session startet) und es bleibt einfach nur das roblox fenster offen.
Prio:  5

Goal:  When the engine runs inside a background session, it draws no on-screen overlay at all, so
       that session shows nothing but the Roblox window. A normal single-session run is completely
       unaffected and keeps the overlay it has today.

Open:  - Where does the engine decide to draw the overlay, and is one condition enough to cover the
         fullscreen overlay and the window-lock visuals together?
       - How should the engine know it is in a background session: read its own Windows session id
         (the GUI already does this via ProcessIdToSessionId, see gui/app/engine_process.py) or be
         told explicitly over the local bridge? Reading it engine-side needs no protocol change and
         cannot get out of sync, so it is the likely answer.
