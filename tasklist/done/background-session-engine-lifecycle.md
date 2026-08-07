Title: Eine idee wie wir das alles machen das es für den user einfach ist also am besten einbinden und
       das man nur eine exe öffnene muss oder das direkt in der gui drin ist und sich automatisch nur
       im remote desktop roblox öffnet und nichts sonst, vielleicht noch die gui oder so anpassen vom
       remote
Completed: 2026-08-07
Commit:    443c0ca

Result: The GUI attaches to an engine running in another Windows session but never shuts it down,
        refuses captures whose overlay would open on an unreachable desktop, and says so in the
        Engine status box. Split 1 of 4 of the background-session feature.
