Title: Eine idee wie wir das alles machen das es für den user einfach ist also am besten einbinden und
       das man nur eine exe öffnene muss oder das direkt in der gui drin ist und sich automatisch nur
       im remote desktop roblox öffnet und nichts sonst, vielleicht noch die gui oder so anpassen vom
       remote
Completed: 2026-08-07
Commit:    -

Result: A "Background Session" tab starts, shows and stops the hidden RDP session itself: a
        throwaway .rdp file, mstsc launched hidden against 127.0.0.2, WTSDisconnectSession the
        moment the session logs on, and WTSLogoffSession to end it. Credentials go into Windows
        Credential Manager through CredWriteW (never a command line, unlike the planned cmdkey),
        and the engine interlock refuses to start while an engine runs on this desktop. Split 2 of
        4 of the background-session feature.
