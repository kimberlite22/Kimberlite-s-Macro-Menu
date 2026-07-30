Title: Man soll ein link für ein private server pasten können dem automatisch gejoined wenn man
disconnected wird
Prio:  2

Goal:  A private server link is stored once in the settings; after a disconnect the macro rejoins
       through that link instead of the normal public rejoin. Empty field = today's behavior.
Files: macro/tower_defense_macro_gui.ahk (CheckDisconnectTick, the DisconnectRestartPending
       restart path, General tab), config.ini [General], the General settings view in gui/
Steps: 1. Add a "Private server link" field to the General settings, persist it under [General].
       2. Validate it is a roblox.com share / private-server URL before storing it.
       3. In the reconnect path, when the field is set, launch the link and wait for the game
          window, then continue into the existing restart path.
       4. Log that a private server rejoin was used, without printing the full link code.
Open:  How does the current reconnect actually re-enter the game (relaunch Roblox vs. clicking a
       rejoin button)? That decides where the link hooks in. Should the link also be used for the
       very first start of a session, not only after a disconnect?
