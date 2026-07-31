Title:     Bug seit mehreren releases: manchmal beim senden eines commands kommt "Command not send
           waiting for previous command to be cleared" und es bleibt für immer stuck. Beim nächsten
           Start manchmal "no readable config.ini found permission failed:13" (Text ungefähr, konnte
           ihn nicht genau ablesen).
Completed: 2026-07-31
Commit:    -

Result: local_cmd.txt older than 90s (past PAIR_REMOTE_AGENT's ~50s worst case) is now treated as
        abandoned and cleared instead of blocking every future command forever; config.ini reads
        retry a few times past a transient Windows sharing violation from a mid-save read; and
        _refresh_config only blanks the GUI to defaults on the very first load, keeping the last
        known-good config (and what Save would submit) on any later transient read failure.
