Title: adde das man auch in der background session capture positions etc. machen kann
       Im moment (denke ich) nimmt das macro die screenshots von dem main desktop zum zweiten
       desktop also wenn ich sagen wir die background session minimiert habe dann funktiert das
       screenshot nehemen nicht mehr weil es nicht offen ist das window. Deswegen baue es ein das
       die screenshots vom macro in der background session genommen werden. Damit kannst du
       ausserdem das feature einbauen das man positionen beim macro editieren auserhalb der
       background session capturen kann in der background session was im moment nicht passiert.
Completed: 2026-08-11
Commit:    -

Result: The screenshots were already being taken inside the background session (ocr_server.exe is a
        child of the engine, which runs there); what stopped them was Windows pausing a Remote
        Desktop session's rendering while its client window is minimized. A "Keep the session's
        screen running while minimized" option in the Background Session tab writes the client-side
        HKCU DWORD RemoteDesktop_SuppressWhenMinimized=2 (no elevation) right before Start and Show
        launch mstsc, which is when the client reads it. Capturing a position from the physical
        desktop no longer refuses: it restores and activates the background session's own client
        window, reconnecting it through Show when there is none, and the engine's overlay is used
        inside that session. A refused activation is reported rather than claimed as success, the
        window is matched only on the branded title or the session address (never "the only Remote
        Desktop window open"), and a module-level guard stops a second capture from re-entering
        while the first is still pumping Qt events. The tab's status line now also names the one
        configuration that silently screenshots the wrong desktop: a background session running
        while an engine is still running on this one.
