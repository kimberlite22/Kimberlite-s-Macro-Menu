Title: yes its way faster but still the first time i start the built .exe one stray gui.exe remains
       in the background
Prio:  1

Goal:  Follow-up from engine-still-not-closing-followup: that task sped up and hardened the shutdown
       path reached when the MAIN window closes (main.py's QApplication.aboutToQuit / closeEvent),
       but the user's own retest still finds a stray gui.exe left behind specifically the very first
       time a freshly built/installed exe is launched. That first launch never reaches the window-
       close path at all: ensure_self_installed() (gui/app/self_install.py) copies itself into
       install_dir(), relaunches the installed copy via subprocess.Popen(..., DETACHED_PROCESS), and
       main() (gui/app/main.py:232-233) returns 0 immediately, before QApplication is even
       constructed - so the earlier fix's aboutToQuit handling cannot be what is leaving a process
       behind here; this is a distinct code path with its own bug.

Files: gui/app/self_install.py (ensure_self_installed, the subprocess.Popen relaunch call),
       gui/app/main.py (main(), the self-install branch at lines ~220-235)

Steps: 1. Reproduce with the user's help (running the app needs their explicit go-ahead per
          CLAUDE.md): build fresh per gui/BUILD.md, launch the freshly built exe from outside the
          install directory (e.g. Desktop/Downloads) for the first time, and once the relaunched
          installed copy's window is up, use Task Manager / Process Explorer to identify exactly
          which gui.exe PID lingers and its command line / working directory, to tell apart the
          original bootstrap process from its relaunched child.
       2. gui.exe is a PyInstaller --onefile build (see gui/BUILD.md), which always launches as a
          bootloader parent plus an extracted child process, exactly like macro/ocr_server.exe and
          the AHK engine exe (see the /T taskkill handling in gui/app/engine_process.py and the
          "Two implementation details worth keeping" note in CLAUDE.md's OCR section) - confirm
          whether the lingering process is this bootloader pair failing to tear down together
          before assuming the bug is unique to the self-install path.
       3. Check whether subprocess.Popen(command, creationflags=DETACHED_PROCESS) in
          ensure_self_installed() implicitly hands the relaunched child (or its own onefile
          bootloader) an inherited handle back to the original process (Python's default
          close_fds=True on Windows only closes non-standard handles; stdin/stdout/stderr are not
          redirected here) that could keep the original bootloader waiting on a pipe/handle that
          never closes; if so, pass explicit closed/redirected stdin/stdout/stderr (e.g.
          subprocess.DEVNULL) to the Popen call, matching how engine_process.py's own Popen calls
          are set up.
       4. If steps 2-3 do not explain it, check whether the delay is actually just slow rather than
          permanent - a brand-new, previously unscanned exe's onefile temp extraction is a known
          trigger for Windows Defender / other AV real-time scanning specifically on first run,
          which would explain "only the first time" without being a bug in this codebase at all;
          have the user time how long the stray process survives and whether it eventually exits on
          its own.
       5. Once the actual mechanism is confirmed, apply the minimal fix (most likely an explicit
          stdio redirect on the relaunch Popen call, or nothing at all if step 4 explains it as an
          AV/OS artifact - report that finding back to the user instead of a code change).

Open:  -
