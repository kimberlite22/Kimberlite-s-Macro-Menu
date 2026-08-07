Title: Eine idee wie wir das alles machen das es für den user einfach ist also am besten einbinden und
       das man nur eine exe öffnene muss oder das direkt in der gui drin ist und sich automatisch nur
       im remote desktop roblox öffnet und nichts sonst, vielleicht noch die gui oder so anpassen vom
       remote
Completed: 2026-08-07
Commit:    -

Result: A "Setup" box in the Background Session tab runs four readiness checks (Remote Desktop
        enabled, fSingleSessionPerUser allowing a second session for the same account, TermService
        loading rdpwrap.dll, and rdpwrap.ini covering this exact termsrv.dll build read from its
        BINARY VS_FIXEDFILEINFO version), shows each one with the concrete instruction for fixing
        it, and gates Start on the overall verdict. Detection only: it never installs, elevates or
        writes to the registry, every check fails closed when it cannot read what it needs, and the
        tab states up front that RDP Wrapper is third-party, not bundled, needs admin plus a reboot,
        and goes beyond Microsoft's licensing intent. Split 3 of 4 of the background-session
        feature.
