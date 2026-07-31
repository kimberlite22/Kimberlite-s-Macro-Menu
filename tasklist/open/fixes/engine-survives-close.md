Title: wenn man die application schließt soll sie nicht mehr im hintergrund laufen
Prio:  2

Goal:  Closing the GUI always also stops the hidden AutoHotkey engine process; no engine instance
       is left running in the background afterward.
Open:  gui/app/main.py only wires `app.aboutToQuit.connect(stop_engine)` when THIS launch itself
       spawned the engine (`spawned_engine is not None`, main.py ~299-300). A launch that instead
       attaches to an engine already running (`engine_running` true - left over from a crash, a
       forced close, or a second GUI instance) never gets an aboutToQuit hook for it, so that
       engine survives every later close and keeps accumulating. Does the fix need an attaching
       launch to adopt ownership of shutdown for the engine it finds already running, or is the
       real complaint a case where closeEvent/aboutToQuit does not fire at all (e.g. the window
       being closed some other way than the normal close button)? Needs the user to say how they
       usually close the app when this happens, before planning the fix in detail.
