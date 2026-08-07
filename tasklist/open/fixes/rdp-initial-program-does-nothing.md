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

ROOT CAUSE, PROVEN 2026-08-07 (investigation round 2; supersedes the guesses below it):
       The mechanism, end to end, established by disassembling the Windows binaries that implement
       it and by calling the same API out of band against the live failing session:
         mstsc "alternate shell" -> RDP Client Info PDU -> termsrv stores it on the WinStation ->
         winlogon runs userinit.exe -> userinit calls ProcesRemoteSessionInitialCommand (sic,
         Microsoft's own typo), an export of userinitext.dll reached through the API set
         ext-ms-win-session-userinit-l1-1-0.dll -> that function calls
         WINSTA.dll!WinStationGetInitialApplication -> which is a thin RPC stub (NdrClientCall3,
         procnum 3) into termsrv.dll -> on success userinitext calls SetCurrentDirectoryW on the
         work directory and then CreateProcessW on the program.
       The failure is at the WinStationGetInitialApplication step, and the launch is NEVER
       ATTEMPTED. Recovered signature (from the disassembly of ProcesRemoteSessionInitialCommand
       at userinitext.dll RVA 0x2C10, call site 0x2D67):
         BOOLEAN WinStationGetInitialApplication(ULONG SessionId, PWSTR *ppApp, PWSTR *ppWorkDir,
                                                 PBOOLEAN pfAllowed, PBOOLEAN pfMaximizeShell);
       Called live against the user's own failing session 14 it returns FALSE, sets last error 2
       (ERROR_FILE_NOT_FOUND), yet fills ppApp with the CORRECT, intact path and leaves ppWorkDir
       NULL and both flags 0. userinitext's failure branch is then exactly:
         test al,al / jne success ; app pointer non-NULL -> string id 1604 + GetLastError()
         -> FormatMessageW(2) + LoadStringW(1604) -> MessageBoxW
       which composes, verbatim, the dialog the user sees:
         "The system cannot find the file specified. This initial program cannot be started: <path>"
       So the "file not found" never referred to the program file at all. It is the RPC's own
       error code, reported through a message template whose %s happens to be the program path.
       That is why point 6 below was right to call the message unreliable, and why nothing about
       the path, the quoting, the arguments, the filename or the apostrophe ever mattered.

WHAT THIS EXONERATES (do not re-investigate):
       - CreateProcessW. Probed directly with the real launcher path in all four argument shapes
         (application name with and without a working directory, unquoted command line, and
         C:\Windows\System32\taskmgr.exe), using CREATE_SUSPENDED plus an immediate
         TerminateProcess so nothing actually ran: ALL FOUR SUCCEED. CreateProcess resolves that
         path, apostrophe and spaces included, without complaint.
       - The transport. The directive arrives intact. WinStationQueryInformationW against session
         14 shows both the program and the work directory stored correctly on the WinStation, in
         WinStationClient (class 6) and in the merged WinStationConfiguration (class 1).
       - RDP Wrapper, the previous prime suspect. Its rdpwrap.ini section for this exact termsrv
         binary build ([10.0.26100.4484]) applies only four patches: LocalOnlyPatch,
         SingleUserPatch, DefPolicyPatch (CDefPolicy::Query) and SLInitHook
         (CSLQuery::Initialize). None of them is anywhere near the initial-program RPC path, and
         its [SLPolicy] overrides are all connection, session-count, redirection and compression
         policies. Combined with the directive arriving intact, RDP Wrapper is not the cause.
       - The AEMSessionShell.exe launcher and the filename-based mode detection from PR #133 are
         confirmed dead weight: they were built to dodge a CreateProcess quoting problem that does
         not exist. See the first Open: item.

WHY THE RPC HANDLER FAILS, PROVEN 2026-08-07 (investigation round 3; this ANSWERS the previous
round's only open question and supersedes both hypotheses below):
       The client-supplied alternate shell is validated against the RemoteApp PUBLISHED
       APPLICATION ALLOW LIST, and on this machine that list is enforced but empty, so the
       lookup misses and reports "not found". Full chain, read out of the binaries with
       Microsoft's public symbols (msdl.microsoft.com):
         userinit -> WinStationGetInitialApplication (RPC)
           -> termsrv!RpcGetInitialApplication              (RVA 0x5C180)
             -> termsrv!ApplyTSAllowPolicyToInitialProgram  (RVA 0x5A524)
               -> termsrv!CConnectionEx::Verify(VERIFY_TYPE_PUBLISHED_APPLICATION)
                  (RVA 0x87260; forwards to the WSX object, GUID
                   c77d1b30-5be1-4c6b-a0e1-bd6d2e5c9fcc)
                 -> rdpcorets!VerifyAppAllowed              (RVA 0x82B80,
                    source clientcore\termsrv\rap\allow\lib\tsallow.cpp)
                   -> IsAllowListDisabled() == FALSE
                      -> VerifyRealAppAllowedFromRegistry() (RVA 0x828A8)
                         -> RegEnumKeyExW over TSAppAllowList\Applications -> EMPTY -> not found

       The gate is rdpcorets!IsAllowListDisabled (RVA 0x8245C). It returns TRUE (meaning
       "enforcement off, allow anything") when EITHER of these is set, and FALSE otherwise:
         - HKLM\Software\Policies\Microsoft\Windows NT\Terminal Services
             fAllowUnlistedRemotePrograms = 1   (REG_DWORD, read by CheckAllowListGroupPolicy,
                                                 RVA 0x81A18)
         - HKLM\Software\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList
             fDisabledAllowList = 1             (REG_DWORD)
       When it returns TRUE, VerifyAppAllowed sets *pbAllowed = 1 and returns S_OK WITHOUT any
       lookup at all. When it returns FALSE, the requested program must match a published entry.
       MEASURED ON THIS MACHINE 2026-08-07: fDisabledAllowList = 0 and the Applications subkey
       has NO entries, so every alternate shell is rejected. That is the entire bug.

       WHY THE ERROR MESSAGE LIES, now explained instruction by instruction: in
       RpcGetInitialApplication the failure branch at 05C70D is entered when
       ApplyTSAllowPolicyToInitialProgram returns 0x80070002 or 0xD0070002 (the WSX layer sets
       bit 28, CWsx::Verify at RVA 0x38370 does "bts ebx, 0x1c", which is why the handler tests
       for both forms). That branch copies the config string at +0x2F2 into *ppCmdLine,
       HARDCODES the return value with "mov ebx, 0x80070002", and never writes ppWorkDirectory.
       That reproduces the previous round's measurement exactly: FALSE, last error 2, correct
       intact path in ppApp, NULL ppWorkDir, both flags 0. ERROR_FILE_NOT_FOUND always referred
       to the allow-list lookup, never to the program file.

BOTH EARLIER HYPOTHESES ARE NOW DISPROVEN (do not spend time on them):
       (i) "not enabled on a client SKU" is WRONG. The gate is a registry allow list that any
           SKU evaluates the same way; nothing in the path tests ProductType or the SKU.
       (ii) "the handler fails resolving the WORK DIRECTORY" is WRONG. The work directory is read
           at 05C623 from config+0xF0 and an EMPTY one is perfectly legal: the copy is skipped and
           *ppWorkDirectory is simply left NULL, which userinitext handles by skipping
           SetCurrentDirectoryW. The work directory is never consulted before the allow-list check,
           so the planned "send no shell working directory line" test would prove nothing and is
           NOT worth running.
       RDP Wrapper is exonerated a second time, now positively rather than by elimination: the
       failure happens downstream of everything it patches, inside rdpcorets' allow-list lookup.

STILL OPEN (small, and only confirmatory):
       - Empirical confirmation that flipping the gate actually makes the shell run. Judge ONLY by
         positive proof (a marker file the probe writes itself), never by Explorer's absence.
       - Reproducing the logon-time call is now optional. The static chain plus the matching error
         code settles the diagnosis; a trace would only re-confirm it. userinitext emits DbgPrint
         diagnostics ("USERINIT: CreateProcess failed with error: %lu", "USERINIT: Logging off
         session since WinStationGetInitialApplication failed!") and a TraceLogging provider
         Microsoft.Windows.Security.UserInit; capturing either needs elevation.

ADDITIONAL ROUTE NOT IN THE LIST BELOW, worth evaluating on its merits:
       e. A dedicated local Windows account for the background session, with
          HKU\<that account's SID>\...\Winlogon\Shell pointing at the app. This removes Explorer
          with no RDP patching at all and no reliance on the broken initial-program path, and it
          also dissolves the shared-profile hazard that currently makes self-gating mandatory.
          Its real costs are a second profile: separate config.ini, separate Roblox login. See the
          user constraint below before pursuing it: it survives ONLY if the app creates and manages
          that account itself.

USER CONSTRAINT ADDED 2026-08-07, verbatim (this is the acceptance bar for every route):
       "yes i can provide that tell me how. And second because you mentioned a dedicated windows
       account. Well that would work but my goal is for the user to press one button, and then to
       have the roblox window open and doing the macro without them even noticing all the
       background stuff so that is too much for them to do which they might mess up and so on."

       What this means, applied to the routes: the END USER performs no setup. Anything a route
       needs must be done BY THE APP, not by hand. Rank the routes on that axis too, not only on
       whether they technically work:
       - Route (c), autostart via HKCU Run or the Startup folder, needs no administrator rights at
         all. It is by far the cheapest on this axis and is the safe fallback.
       - Routes (b) and (e) both need administrator rights (HKLM write; local account creation).
         That is NOT automatically disqualifying: the product ALREADY has a one-time elevated
         setup step, since RDP Wrapper has to be installed and the Background Session tab has a
         setup wizard for it. An admin action folded into that existing flow is acceptable; an
         admin action the user has to hand-craft is not.
       - Route (e) is therefore only viable fully automated: the app creates the local account,
         sets its shell, stores its credential and hides it from the sign-in screen, all from the
         one button. Do not propose it as "the user makes an account".

HOW TO GIVE THE NEXT SESSION ELEVATION (the user asked how; answer recorded here so it is not
lost):
       Preferred, simplest: close VS Code, start it AS ADMINISTRATOR (right click the shortcut ->
       Run as administrator), reopen this repo and start the Claude session there. Every
       PowerShell and Bash tool call then runs elevated. The session can verify with
         ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
       which must print True (it printed False for the investigating session).

       Scoped alternative, if elevating the whole IDE is unwanted: from ONE elevated PowerShell
       window the user registers a helper task once,
         New-Item -ItemType Directory C:\AEMElevated -Force
         $a = New-ScheduledTaskAction -Execute 'powershell.exe' `
              -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\AEMElevated\run.ps1'
         $p = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest
         Register-ScheduledTask -TaskName 'AEMElevatedHelper' -Action $a -Principal $p
       after which a session writes C:\AEMElevated\run.ps1, runs
       "schtasks /run /tn AEMElevatedHelper" and reads the output the script writes to a file.
       Runs as SYSTEM, which is fine (better, actually) for ETW capture and HKLM writes. Remove it
       afterwards with Unregister-ScheduledTask -TaskName 'AEMElevatedHelper'.

WHERE THE NEXT SESSION PICKS UP:
       Both the root cause AND the reason the RPC handler fails are proven; neither needs
       re-deriving, and the route is decided. What is left is confirmation and then implementation:
       1. CONFIRM EMPIRICALLY, with elevation. Set fDisabledAllowList = 1 (route a2, the cheap
          switch), start a background session whose .rdp carries a marker-writing probe as the
          alternate shell, and check the marker file. Judge ONLY by positive proof the program ran,
          never by Explorer's absence (see the methodological warning above). Then set it back to 0
          and confirm the failure returns, which makes the causal link airtight rather than
          correlational.
       2. IMPLEMENT route (a1): have the app write its own TSAppAllowList\Applications entry from
          the existing one-time elevated setup flow (the RDP Wrapper wizard in the Background
          Session tab), and remove it again when the feature is turned off. Then re-test with the
          real launcher instead of the probe.
       3. Only after (1) and (2) work, revisit the Open: items below (the dead AEMSessionShell.exe
          launcher from PR #133, and whether the Roblox share link actually opens in that session,
          which has still never been observed because the shell never ran).
       4. Reproducible tooling from this round, in <job scratchpad>/tmp, worth rebuilding rather
          than reinventing. The key unlock was Microsoft's PUBLIC SYMBOLS, which turn this from
          guesswork into reading named functions:
            - get_pdb.py: parses a PE's CodeView debug entry and downloads the matching PDB from
              https://msdl.microsoft.com/download/symbols/<pdb>/<GUID><Age>/<pdb>.
            - syms.py: ctypes wrapper over System32 dbghelp.dll (SymInitialize / SymLoadModuleEx /
              SymEnumSymbols) to list symbols with RVAs. Declare argtypes on EVERY call: passing the
              handle as 32-bit to one and 64-bit to another fails with ERROR_INVALID_HANDLE.
            - disasm.py: capstone + pefile, resolving call targets to PDB symbol names and IAT
              imports and rip-relative operands to string literals. "python -m pip install capstone"
              (plain, no --target; the --target form was blocked by the permission classifier).
            - a ctypes probe calling WinStationGetInitialApplication with the signature recorded
              above. Load winsta.dll with use_last_error=True or ctypes clobbers the error code.
          Note .pdata-derived function bounds are wrong for a few symbols (CSLQuery::GetInitialProgram
          reports a 0xC008 "size" that spans many functions); trust the disassembly, not that number.
       5. Session 14 was ACTIVE and in use throughout and must stay that way; the console session
          (id 1) must never be logged off.

OLD OPEN QUESTIONS, ALL NOW ANSWERED (kept only so nobody reopens them):
       - How the initial program travels and who executes it: answered in full by the two chains
         above, from the RDP Client Info PDU through termsrv and userinitext to CreateProcessW.
       - Whether RDP Wrapper is the cause: NO. Ruled out twice, the second time positively: the
         failure is inside rdpcorets' allow-list lookup, downstream of every offset rdpwrap.ini
         patches. The two reported termsrv.dll versions (binary 10.0.26100.4484, string
         10.0.26100.8875) are a red herring for this bug.
       - Whether client SKUs support a client-supplied initial program at all: moot. The gate is a
         registry allow list, not a SKU or licensing check, and it evaluates the same everywhere.
       - What the session does at logon when the directive is present: it has no shell because
         userinitext bails out at the failed RPC before launching anything, which is also why
         Explorer is absent. Enumerating those ~17 processes would add nothing now.

ROUTE DECISION (the mechanism is now understood, so this list is decided, not open):
       ROUTE (a) IS THE ONE TO BUILD, and it is now a known, small, reversible change rather than a
       hope. The alternate shell path is not broken; it is gated. Publish the app in the allow list
       and the gate opens. Two concrete shapes, in order of preference:

       a1. PUBLISH ONLY OUR EXE (preferred). Create
             HKLM\Software\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList\
               Applications\<alias>
           with the values VerifyRealAppAllowedFromRegistry / DoesAppMatchAllowListEntry
           (RVA 0x828A8 / 0x834AC) actually read: Path (matched case-insensitively via
           CompareStringW against Path, ShortPath and LongPath), plus CommandLineSetting and
           RequiredCommandLine, which VerifyCommandLine (RVA 0x8360C) checks. Allow-list
           enforcement stays ON for everything else; only our binary becomes launchable. This is
           the tighter change and is what the app should write.
       a2. DISABLE THE ALLOW LIST WHOLESALE: fDisabledAllowList = 1 (or the group policy
           fAllowUnlistedRemotePrograms = 1). One value, definitely works, but it lets ANY program
           be launched as a remote app over RDP by anyone who can already authenticate. Keep it as
           the fallback and as the first thing to try when confirming the diagnosis empirically,
           not as what ships.

       Both need administrator rights (HKLM write) and both are trivially reversible, which the
       user constraint explicitly permits: the product ALREADY has a one-time elevated setup step
       for RDP Wrapper, and the Background Session tab already has a wizard for it. The end user
       still presses one button; the app does the registry write from that existing elevated flow.
       Route (a) is also the only route that genuinely removes Explorer, which was always its
       appeal, so the low-RAM benefit survives.

       b. Per-WinStation InitialProgram: HKLM\...\WinStations\RDP-Tcp\InitialProgram plus
          fInheritInitialProgram=0 makes the SERVER dictate the program for every RDP connection.
          NOW KNOWN TO BE POINTLESS AS A WORKAROUND, and the previous round's prediction was right
          for a sharper reason than it knew: the allow-list check in ApplyTSAllowPolicyToInitialProgram
          runs on the MERGED configuration regardless of whether the program came from the client or
          from this registry value, so a server-dictated program is verified against the same empty
          allow list and fails identically. Do not build on it. It also affects any other RDP use,
          which route (a1) does not.
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
