Title: Man soll ein link für ein private server pasten können dem automatisch gejoined wenn man
disconnected wird

       Wenn es geht dann mach es so das die externe session started direkt das roblox mit dem link
       sich öffnet. Dann kann man das macro starten.
Prio:  2

Goal:  A private server link is stored once in the settings and used in two places: after a
       disconnect the macro rejoins through it instead of the normal public rejoin, and starting a
       background session opens Roblox straight into that server so the macro can be started right
       after. Empty field = today's behavior in both places.
Files: macro/tower_defense_macro_gui.ahk (CheckDisconnectTick, the DisconnectRestartPending
       restart path, General tab), config.ini [General], the General settings view in gui/,
       gui/app/background_session.py (launching the link inside the new session)
Steps: 1. Add a "Private server link" field to the General settings, persist it under [General].
       2. Validate it is a roblox.com share / private-server URL before storing it. Accept the
          current share format the user supplied as the reference case:
          https://www.roblox.com/share?code=<hex>&type=Server
          It resolves server-side and then hands off to the Roblox protocol handler, so launching
          the URL is enough; there is no need to resolve the code in-process.
       3. In the reconnect path, when the field is set, launch the link and wait for the game
          window, then continue into the existing restart path.
       4. Log that a private server rejoin was used, without printing the full link code.
       5. Background session start: once the session is up, launch the same link inside it so
          Roblox comes up already in the private server. Note that the handoff goes through the
          default browser, so a browser window appears briefly, and the Roblox account has to be
          signed in inside that session. Coordinate with
          [[background-session-minimal-shell]], which removes Explorer from that session.
Open:  How does the current reconnect actually re-enter the game (relaunch Roblox vs. clicking a
       rejoin button)? That decides where the link hooks in.
       (Resolved 2026-08-07: yes, the link is also used for the first start of a session, not only
       after a disconnect. That is step 5 above.)
