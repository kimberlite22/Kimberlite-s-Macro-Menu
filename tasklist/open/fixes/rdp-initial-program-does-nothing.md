Title: While the session runs with the macro investigate the rdp mechanism further. Youre allowed to
       make deep changes in the infrastructure there if you think that might help. Investitage first
       before writing any code and find out down to the roots how that mechanism works and how we can
       modify the rdp procedure to work in our favor.
Prio:  1

Goal:  Understand, at the level of the actual Windows mechanism, why an RDP "alternate shell" starts
       nothing on this machine, and then make "Boot straight into the macro" work (Roblox open on the
       configured private server, the engine running, ideally no Explorer) by whatever route that
       understanding shows to be correct. Deep infrastructure changes are explicitly sanctioned by
       the user. INVESTIGATE FIRST, WRITE NO CODE UNTIL THE MECHANISM IS UNDERSTOOD. That is a direct
       instruction, not a preference.

STATE WHEN THIS WAS FILED (2026-08-07, ~09:55):
       A background session IS RUNNING and in use: session id 14, rdp-tcp#0, ACTIVE, owned by
       fleet/PCVONTIM, tracked in <DataDir>\background_session_state.json, with mstsc pid 20392
       holding it from the console session. Do NOT log it off while investigating. The user is
       running the macro in it. Sessions can be listed with "query session" and the console session
       (id 1) must never be logged off.
       The user's current workaround: the error dialog still appears on Start with the box ticked,
       they click it away and use the session anyway.

WHAT IS PROVEN (do not re-derive this, it cost several rounds):
       1. The RDP alternate shell starts NOTHING on this machine. A purpose-built probe executable
          whose only job is to append a line to a marker file the instant it runs was used as the
          alternate shell: the marker file was never written. It never executed at all.
       2. It is not about our path, our quoting, our filename or the apostrophe in the install
          folder. C:\Windows\System32\taskmgr.exe, a clean path with no spaces, also never started.
       3. It is not about the executable being unstartable. The launcher
          (%LOCALAPPDATA%\Programs\Kimberlite's Macro Menu\AEMSessionShell.exe) runs fine from the
          console session: "AEMSessionShell.exe --help" prints argparse's help. It has no
          Mark-of-the-Web (no Zone.Identifier stream) and is not AV-blocked.
       4. Policy allows it: HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp
          has fInheritInitialProgram = 1, InitialProgram empty, WorkDirectory empty, and there is no
          HKLM\SOFTWARE\Policies\...\Terminal Services override.
       5. Specifying an alternate shell produces a session with NO shell at all: Explorer does not
          run either, and the session sits at about 17 processes. So the directive is not simply
          ignored (that would leave Explorer); something consumes it and then fails.
       6. Windows reports "The system cannot find the file specified. This initial program cannot be
          started: <path>" for a path that demonstrably exists. Treat that message as unreliable.

METHODOLOGICAL WARNING THAT ALREADY CAUSED ONE WRONG FIX:
       An earlier round judged "did the alternate shell work" by whether Explorer was absent from the
       session. Explorer is ALSO absent when the shell fails to start, so a failure was read as a
       success and a fix was shipped (the AEMSessionShell.exe launcher, PR #133) that could not
       possibly have helped. Judge only by positive proof that the target program actually executed,
       for example a marker file it writes itself. The probe used for this is described above and is
       trivial to rebuild.

WHAT IS NOT YET KNOWN (this is the actual work):
       - How the initial program travels and who executes it: the client puts "alternate shell" into
         the RDP connection PDU, the server side stores it on the WinStation/session, and winlogon
         or userinit launches it instead of the configured shell at logon. Establish which component
         on THIS machine is meant to do that, and instrument or trace it rather than guessing.
       - Whether RDP Wrapper is the cause. It patches termsrv.dll in memory (rdpwrap.dll plus the
         offsets in rdpwrap.ini for this exact termsrv build). If its patches bypass or zero the
         code path that reads the client's initial program, this would fail exactly as observed,
         while fInheritInitialProgram still reads 1 because nothing ever consults it. This is the
         prime suspect. Note the machine reports two different termsrv.dll versions (binary
         10.0.26100.4484, string 10.0.26100.8875) and rdpwrap.ini has a section for the binary one;
         see setup-wizard-undetermined-checks in tasklist/done/ for why the binary one is the key.
       - Whether Windows client SKUs support a client-supplied initial program for a full desktop
         session at all, as opposed to Server SKUs. Find the authoritative answer, not a forum guess.
       - What the session actually does at logon when the directive is present: the 17 remaining
         processes are worth enumerating and comparing against a normal session, and the new
         session's own event log entries around logon time should be read.

ROUTES TO EVALUATE ONCE THE MECHANISM IS UNDERSTOOD:
       a. Fix the alternate shell path properly, if it turns out to be an RDP Wrapper patch gap or a
          WinStation setting we can legitimately set. Preferred if achievable, since it is the only
          route that genuinely removes Explorer.
       b. Per-WinStation InitialProgram: HKLM\...\WinStations\RDP-Tcp\InitialProgram plus
          fInheritInitialProgram=0 makes the SERVER dictate the program for every RDP connection.
          Machine-wide and affects any other RDP use, needs admin, and must be reversible. Evaluate
          honestly rather than reaching for it.
       c. Autostart instead of shell replacement: a Startup-folder entry or HKCU Run value launching
          the app in session-shell mode, with the app exiting IMMEDIATELY when it finds itself in the
          console session so the physical desktop is untouched (both sessions share one profile, so
          self-gating is mandatory, not optional). Explorer stays, which loses the low-RAM benefit
          but delivers the user's ORIGINAL request: Roblox opens on the private server and the macro
          can then be started. Optionally close Explorer from inside afterwards, with the control
          window's "Start Explorer" button as the way back.
       d. Do not silently keep offering a checkbox that produces a broken session. Whatever route is
          taken, the option must either work or not be offered.

Files: gui/app/background_session.py (_rdp_file_lines writes the alternate shell and shell working
       directory), gui/app/session_shell.py (session_shell_command, session_shell_available,
       run_session_shell, and the session_shell_log.txt diagnostics added earlier),
       gui/app/self_install.py (ensure_session_shell_launcher creates AEMSessionShell.exe as a hard
       link), gui/app/main.py (_is_session_shell_executable and the session-shell branch),
       gui/app/rdp_wrapper.py (reads termsrv.dll's binary version and the rdpwrap.ini sections)

Open:  - If route (a) proves impossible, the AEMSessionShell.exe launcher and the filename-based mode
         detection from PR #133 become dead weight and should be removed rather than left behind as
         a monument to a wrong diagnosis. The --session-shell flag itself stays useful either way.
       - Roblox opening via the share link has still NEVER been observed to work, because the shell
         never ran, so it remains completely untested rather than known-good or known-broken. The
         second suspect once the shell starts is os.startfile's handoff through the default browser
         in a session with no Explorer. session_shell_log.txt records whether the launch was
         attempted and what it returned.
       - The user's Roblox account must be signed in inside that session for a private server link to
         land anywhere. Confirm before treating a clean log as a code bug.
