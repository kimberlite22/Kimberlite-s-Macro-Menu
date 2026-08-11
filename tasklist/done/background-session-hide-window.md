Title: Also nach einigem testen (ohne deine changes) Habe ich bestätigt das die detections nur
       funktionieren wenn die background session im vordergrund ist, also man muss nciht
       reingetabbed sein aber das bild muss visible auf dem screen sein damit das macro
       funktioniert. Hat sich das mit deinen changes geändert? Wenn nicht fixe das
Completed: 2026-08-11
Commit:    -

Result: The observation was reproduced from the machine's own state rather than taken on trust:
        RemoteDesktop_SuppressWhenMinimized was absent (Windows' suppressing default), and the
        engine plus both ocr_server.exe processes were in the background session, so the screen
        the macro reads is the one Windows stops drawing when the window is minimized.
        background-session-capture already writes that setting, so the answer to "has it changed"
        is yes for the minimized case, but it left two gaps and this task closes them. A Hide
        button minimizes the session's window as its own action, and because a Remote Desktop
        client only reads the setting when it CONNECTS, Hide reconnects the client first whenever
        the setting was written just now (SettingChangeResult gained `changed`;
        ensure_background_session_visible gained force_reconnect so the reconnect is not skipped
        for a window that already exists). Hide refuses outright when the user wants rendering and
        the setting could not be confirmed, pointing at Disconnect instead of minimizing into a
        screen that has stopped being drawn, and its result says which of the two states it left
        the session in rather than always claiming the good one. The status line now also names
        the state itself, so "it only works while I can see it" is answered in the GUI instead of
        having to be discovered by watching detection stop.
