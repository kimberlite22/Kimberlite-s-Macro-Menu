Title: Eine idee wie wir das alles machen das es für den user einfach ist also am besten einbinden und
       das man nur eine exe öffnene muss oder das direkt in der gui drin ist und sich automatisch nur
       im remote desktop roblox öffnet und nichts sonst, vielleicht noch die gui oder so anpassen vom
       remote
Prio:  2

Goal:  The GUI handles an engine that runs in a DIFFERENT Windows session correctly: it still
       attaches to it over the local bridge (both sessions share one user profile, so the bridge
       files are literally the same files), but it never takes shutdown ownership of it, and it
       refuses the capture actions that cannot work across sessions. This is the foundation slice
       of the background-session feature: without it, closing the GUI on the physical desktop kills
       the macro running in the background session. Split 1 of 4 from the same request, see
       [[background-session-launcher]], [[background-session-setup-wizard]] and
       [[background-session-minimal-shell]].

Files: gui/app/engine_process.py    is_engine_running() / get_engine_pid(): the tasklist.exe scrape
                                   filters on IMAGENAME only, so it matches an engine in ANY
                                   session. Needs the Session# column plus a current-session helper.
       gui/app/main.py:271-319      the attach path sets attached_engine_pid unconditionally and
                                   wires stop_owned_engine into app.aboutToQuit, which is what
                                   kills a background engine when the GUI closes.
       gui/app/main_window.py:1175  _capture_placement, the capture entry point.
       gui/app/capture.py           capture_point / capture_region drive the overlay through the
                                   bridge, so the crosshair is drawn ENGINE-side, on the desktop of
                                   whichever session the engine lives in.
       gui/tests/test_engine_process.py, gui/tests/test_main_window.py

Steps: 1. Add current_session_id() to engine_process.py via kernel32 ProcessIdToSessionId on the
          current process, returning None when it cannot be determined (keep the existing lazy
          _kernel32() pattern, and the module must stay importable off Windows).
       2. Extend the tasklist.exe CSV scrape to also read the Session# column (row index 3) and
          return pid plus session id together. Keep get_engine_pid() as a thin wrapper so the
          existing call sites and tests keep working.
       3. In main.py, take shutdown ownership ONLY when the found engine's session equals the
          current session. For an engine in another session, still attach and use it (the bridge
          files are shared), but never connect stop_owned_engine for it.
       4. Surface the state in the GUI so the difference is not silent: the user must be able to
          see that the engine runs in a background session and that closing the GUI leaves it
          running.
       5. Guard the capture actions: when the engine is in another session, refuse with a clear
          English message pointing at the background session, instead of drawing a crosshair onto
          a desktop the user cannot see or click.
       6. Tests: session-aware detection, ownership taken for a same-session engine and NOT taken
          for a cross-session one, and the capture guard.

Open:  Whether the background-session state gets its own indicator or reuses the existing engine
       status area. Decide while implementing step 4, no user input needed.
