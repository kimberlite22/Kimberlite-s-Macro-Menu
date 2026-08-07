Title: Remove the AEMSessionShell.exe launcher and its filename-based mode detection, which were
       built to dodge a CreateProcess quoting problem that does not exist.
Prio:  1

Goal:  The separate AEMSessionShell.exe launcher and the "which mode am I in" detection that reads
       the running executable's own filename are gone, and session-shell mode is selected only by
       the --session-shell flag. Follow-up from rdp-initial-program-does-nothing: PR #133 added them
       to work around a supposed CreateProcess quoting/argument problem, and the investigation then
       proved that CreateProcess resolves the real installed path fine (apostrophe and spaces
       included) in all four argument shapes. The launcher never helped, and its own probe never ran
       either, because the real failure was the RemoteApp allow-list lookup in termsrv.

Files: gui/app/self_install.py (ensure_session_shell_launcher, which hard-links or copies
       gui.exe to AEMSessionShell.exe on every managed frozen startup),
       gui/app/launcher_paths.py (SESSION_SHELL_EXE_NAME, session_shell_exe_path),
       gui/app/main.py (_is_session_shell_executable and its use in the session_shell_mode
       expression; the --session-shell flag itself STAYS, it is how both remaining routes are
       expressed), gui/app/session_shell.py (session_shell_command, session_shell_available),
       gui/app/background_session_tab.py (boot_route's shell-availability half),
       gui/tests/test_self_install.py, gui/tests/test_launcher_paths.py,
       gui/tests/test_session_shell.py, gui/tests/test_background_session_tab.py

Steps: 1. Decide what the alternate shell should point at now that the launcher is going. It cannot
          carry arguments (it is CreateProcess's application name, not a command line), so removing
          the launcher means the shell route needs another way to say "start in session-shell mode".
          Check this FIRST, because it decides whether this task is a deletion or a swap: the
          honest options are keeping a tiny launcher purely as an argument-free entry point (in
          which case only the WRONG RATIONALE and the dead comments go, not the file), or dropping
          the alternate-shell route entirely and keeping only autostart. Do not assume the first
          option is available without re-reading how main.py picks its mode.
       2. Whichever option step 1 selects, remove _is_session_shell_executable if the filename is no
          longer how the mode is chosen, and delete ensure_session_shell_launcher plus its call in
          main.py's managed-frozen startup block if the launcher itself goes.
       3. Clean up any leftover AEMSessionShell.exe already installed under
          %LOCALAPPDATA%\Programs\<AppName>, the way cleanup_legacy_installation retires an
          installation left by an earlier name. A file the app stopped creating but never removes is
          exactly the litter this task exists to clear.
       4. Update the comments that still explain the launcher as a CreateProcess quoting workaround
          (launcher_paths.py's SESSION_SHELL_EXE_NAME block and session_shell_command's docstring):
          they document a diagnosis that was disproved, so leaving them behind would send the next
          reader back down the same wrong path.
       5. Run python -m pytest -q in gui/ and fix the tests that pin the removed names.

Open:  - Step 1 is a real decision, not a formality. If the alternate-shell route has to keep an
         argument-free entry point, then this task shrinks to deleting the wrong rationale and the
         dead filename-detection, and the file itself stays with an honest comment explaining that
         an RDP alternate shell simply cannot take arguments.
