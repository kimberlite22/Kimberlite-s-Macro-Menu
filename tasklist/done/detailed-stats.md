Title:     Zu den application stats soll session time, time spent in screen x und time spent repeating
           step x. Die stats sollen auch zur internet website geaddet werden. Du kannst in der gui die
           kommt wenn das macro aktiv ist die rechte untere box anpassen zu so ähnlich wie application
           stats nicht mehr nur raw text wie logs, zu den werten die geaddet werden sollen
Completed: 2026-08-02
Commit:    -

Result: Application Stats gains a Session Time cell; the AHK overlay's old plain-text "Screen Run
        Counts" box is replaced with real ListView tables of per-screen and per-step time (both
        cumulative and, for the running step, current-repetition time); all three reset on every
        restart including internal ones; the same stats reach the remote website live plus as
        persisted session history (new device_sessions table, archived on a session-boundary
        sessionId change, new GET /api/devices/:id/sessions route, new dashboard sections).
