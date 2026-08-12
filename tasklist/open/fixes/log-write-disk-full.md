Title: what happens when macro log is trying to write but there is no space left on the disk. We
       need a fix for that.
Prio:  3

Goal:  A full disk degrades visibly instead of silently. Today LogMsg()
       (macro/tower_defense_macro_gui.ahk:3711) appends the line under a bare try, and the same
       bare-try pattern guards the crash handler's own log write at :137, so a write that
       fails because the volume is full throws, is swallowed, and nothing anywhere says the log
       stopped recording. The on-screen panel keeps scrolling, so the run looks healthy while
       macro_log.txt silently stops at the last successful line, which is exactly the file someone
       would go read afterwards to find out what went wrong.

       Two halves worth separating when planning this. First, NOTICING: a failed write should be
       reported once (not once per line, or the failure itself becomes the flood) through a channel
       that does not need the disk, and the local bridge status is the natural one since the GUI
       already renders it. Second, NOT FILLING THE DISK IN THE FIRST PLACE: macro_log.txt is
       explicitly a full history that is never truncated across runs (see ClearLog()'s comment at
       :3705, which clears only the in-memory panel), so on a long-lived install it grows without
       any bound at all. Whether this task also adds rotation or a size cap is the main scoping
       decision.

       The same failure mode reaches more than the log: config.ini writes, config_backups/, the OCR
       request/response files and the three bridge status files all write to the same volume, and
       an atomic .tmp + FileMove pair fails the same way. Judge how far to go, but the structural
       fix is a single place that decides what a failed write means, not one more bare try per call
       site (see CLAUDE.md's "fix the structural problem, not just the symptom").

Open:  - Scope: notification only, or notification plus log rotation / a size cap? Rotation is the
         part that actually prevents this app from being the thing that fills the disk, but it
         changes a file the user may be tailing and is a bigger change than the report asks for.
       - Whether a full disk should also stop the macro. A run that cannot write its log can still
         click correctly, so stopping is arguably wrong, but a run nobody can diagnose afterwards
         is close to worthless. Ask before choosing.
       - How to tell "disk full" apart from the ordinary transient failure the bare try was
         written for (the log file momentarily locked by an editor or a virus scanner). Treating
         every failed append as a full disk would cry wolf; check what AutoHotkey reports in
         A_LastError / the thrown OSError for ERROR_DISK_FULL (112) and ERROR_HANDLE_DISK_FULL (39)
         before designing the message.
