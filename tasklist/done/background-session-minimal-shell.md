Title: Eine idee wie wir das alles machen das es für den user einfach ist also am besten einbinden und
       das man nur eine exe öffnene muss oder das direkt in der gui drin ist und sich automatisch nur
       im remote desktop roblox öffnet und nichts sonst, vielleicht noch die gui oder so anpassen vom
       remote
Completed: 2026-08-07
Commit:    -

Result: A new --session-shell mode makes the app itself the background session's Windows shell via
        the .rdp "alternate shell" directive, so that session comes up with the engine, optionally
        Roblox (from a configured private server link), and no Explorer, desktop or start menu.
        Both open questions are answered: the mode never returns before its Qt event loop, since
        returning would log the session off, so self-install is skipped and every startup step is
        individually best-effort; and a small always-on-top control window that cannot be minimized
        or closed is the way back in, offering Start Roblox, Start Explorer and Sign out. The option
        is only offered when an installed executable actually exists to point the shell at. Split
        4 of 4 of the background-session feature.
