Title: not working
Prio:  1

Goal:  Follow-up from engine-survives-close: after that fix, closing the GUI still does not
       reliably stop the engine and/or close its secondary windows as intended (the user's
       PENDING_REVIEW.md verdict was just "not working", no further detail given).
Files: gui/app/engine_process.py (get_engine_pid / stop_engine_by_pid), gui/app/main_window.py
       (closeEvent)
Steps: Blocked on Open below: ask the user what specifically still fails (engine keeps running
       after close vs. a secondary window still blocks quitOnLastWindowClosed vs. something else)
       before writing implementation steps.
Open:  What exactly is still broken when closing the GUI: does the AHK engine still keep running
       in the background, does the app itself fail to quit, or something else? Need a repro before
       this can be planned in detail.
