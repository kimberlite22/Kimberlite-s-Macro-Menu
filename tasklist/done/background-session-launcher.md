Title: Eine idee wie wir das alles machen das es für den user einfach ist also am besten einbinden und
       das man nur eine exe öffnene muss oder das direkt in der gui drin ist und sich automatisch nur
       im remote desktop roblox öffnet und nichts sonst, vielleicht noch die gui oder so anpassen vom
       remote
Prio:  7

Goal:  The GUI can start, show and stop the background session itself, so the user never types an
       mstsc command. Starting writes a temporary .rdp file, launches mstsc hidden, waits until the
       new session is active (WTSEnumerateSessions), then immediately disconnects it
       (WTSDisconnectSession) so the session keeps running with no client attached. A second action
       reattaches for a look. Credentials go into the Windows Credential Manager (cmdkey, DPAPI
       protected), never into config.ini. Split 2 of 4 from the same request; depends on
       [[background-session-engine-lifecycle]], see also [[background-session-setup-wizard]] and
       [[background-session-minimal-shell]].

Open:  - Must connect to 127.0.0.2, not localhost / 127.0.0.1: Windows maps those to the console
         session and fails with error 0x708 even when RDP Wrapper is working correctly.
       - Same Windows account in both sessions (what makes the shared bridge files work) means two
         macro instances could write the same files. Needs a hard interlock before this ships.
       - Credential handling is security relevant, so per CLAUDE.md it is implemented directly and
         not delegated to Codex.
