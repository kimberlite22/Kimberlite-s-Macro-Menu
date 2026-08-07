Title: Wenn das möglich ist dann, ändere auch das desktop icon von der remote verbindung zu dem app
       icon was wir normal benutzen und den namen auch (wobei ich hab zweifel ob das geht)
Completed: 2026-08-07
Commit:    -

Result: The mstsc window that Show opens now carries this app's own title
("Kimberlite's Macro Menu - Background Session") and this app's own icon in its title bar and
taskbar entry, instead of presenting itself as a generic Remote Desktop connection. New
gui/app/window_branding.py does the Win32 work (EnumWindows filtered to the client's visible,
unowned top-level windows, then WM_SETTEXT and WM_SETICON); show_background_session hands the
launched client's pid out through the new BackgroundSessionResult.client_pid, and the tab drives a
bounded 15 second retry, since mstsc rewrites its own title and icon as the connection comes up.

The .lnk half of the original Open questions was dropped, deliberately: this app never hands the
user a .rdp file or creates a desktop shortcut for the session, so there is nothing there to
rebrand and a new shortcut would be an unrequested extra desktop entry. Only Show opens a visible
mstsc window (Start's is launched hidden), so that one window is the whole deliverable, which is
what the user was actually asking about.

Four defects were found by review and fixed rather than papered over:

- Blocking the GUI thread. The retry originally ran on a QTimer calling SendMessageW, which blocks
  indefinitely against an unresponsive window. Switching to SendMessageTimeoutW with
  SMTO_ABORTIFHUNG only bounded each call, so the whole retry now runs on a daemon thread instead,
  with run_branding_loop kept completely free of Qt so running it off the GUI thread is safe.
  Cancellation is a threading.Event and is never joined from the GUI thread, since joining would
  reintroduce exactly the freeze this removed.
- Process id reuse. Windows does not recycle a pid while a handle to that process is open, but the
  launcher's Popen was being discarded, so an mstsc that exited mid-retry could have its id reused
  and an unrelated program's window branded. The Popen is now carried out on the result and held
  both by the tab and, via keep_alive, on the worker's own frame, which also covers a pass still in
  flight after cancellation. Stop cancels branding too.
- An icon that could not be loaded suppressed the title as well, so a build with no resolvable
  app.ico kept the generic name. Title and icon are now independent.
- A never-cleared "already iconned" handle cache was wrong in both directions (stale handles after
  reuse, and no re-assert when mstsc set its own icon during the retry). Replaced by a WM_GETICON
  comparison against our own handles, checking BOTH icon sizes, since the taskbar shows the small
  one and mstsc can replace it alone.

Failure is total and silent throughout: no window found, no icon, a missing symbol, a timed-out
message or a non-win32 platform all leave Show working exactly as before. Verified with the full
gui/ pytest suite (374 passed) run outside the Codex sandbox, which has no Python interpreter;
gui.exe was never launched, per CLAUDE.md.
