Title: Eine idee wie wir das alles machen das es für den user einfach ist also am besten einbinden und
       das man nur eine exe öffnene muss oder das direkt in der gui drin ist und sich automatisch nur
       im remote desktop roblox öffnet und nichts sonst, vielleicht noch die gui oder so anpassen vom
       remote
Prio:  13

Goal:  The background session boots straight into Roblox plus the macro engine and nothing else: no
       Explorer, no desktop, no start menu. Achieved through the .rdp "alternate shell" directive
       pointing at a small launcher, so it needs no scheduled task and no per-account registry
       change. Saves RAM and CPU in the background session as a side effect. Split 4 of 4 from the
       same request; depends on [[background-session-launcher]], see also
       [[background-session-engine-lifecycle]] and [[background-session-setup-wizard]].

Open:  - When the alternate shell exits, Windows logs the session off, so the launcher has to stay
         alive for as long as the macro should run.
       - Needs a way back to a normal desktop in that session for troubleshooting, otherwise a
         broken launcher makes the account hard to get into.
