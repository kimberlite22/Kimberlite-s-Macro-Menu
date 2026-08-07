Title: Eine idee wie wir das alles machen das es für den user einfach ist also am besten einbinden und
       das man nur eine exe öffnene muss oder das direkt in der gui drin ist und sich automatisch nur
       im remote desktop roblox öffnet und nichts sonst, vielleicht noch die gui oder so anpassen vom
       remote
Prio:  8

Goal:  A guided setup in the GUI gets any user from "nothing installed" to a working background
       session: it detects whether RDP Wrapper is installed and actually functional, and walks the
       user through the remaining steps when it is not. Split 3 of 4 from the same request; depends
       on [[background-session-launcher]], see also [[background-session-engine-lifecycle]] and
       [[background-session-minimal-shell]].

Open:  - RDP Wrapper must NOT be bundled into the release. Several antivirus products classify it
         as riskware, and the self-updater pulls from GitHub releases, so a flagged binary would
         break updates for every user. Detect and guide, let the user install it.
       - Detection has to read the BINARY VS_FIXEDFILEINFO version of termsrv.dll, not the string
         resource: they disagree (observed 2026-08-07: string said 10.0.26100.8875, binary said
         10.0.26100.4484) and only the binary one matches the rdpwrap.ini section names.
       - Installing needs admin elevation plus a reboot, which cannot be designed away, only
         packaged into a clear flow.
       - Running several sessions on a Windows client edition is outside what Microsoft's licensing
         intends. Shipping this to all users is a different risk posture than one user doing it
         locally; the user chose to ship it, but the wizard should say what it does.
