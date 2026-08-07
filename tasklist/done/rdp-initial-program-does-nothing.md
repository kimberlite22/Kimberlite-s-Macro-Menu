Title: While the session runs with the macro investigate the rdp mechanism further. Youre allowed to
       make deep changes in the infrastructure there if you think that might help. Investitage first
       before writing any code and find out down to the roots how that mechanism works and how we can
       modify the rdp procedure to work in our favor.
Completed: 2026-08-07
Commit:    -

Result: Root cause proven and fixed. Windows validates an RDP session's initial program against the
        RemoteApp published-application allow list, which is enforced but empty by default, so the
        program was never launched and the session came up with no shell at all. "Boot straight into
        the macro" now takes whichever of two routes actually works on the machine: the alternate
        shell once the allow list is switched off (one reversible, in-app elevated click, genuinely
        no Windows desktop), or an HKCU Run entry needing no administrator rights (Explorer stays).
        The option now always describes what it will really do instead of promising a missing
        desktop it could not deliver.

PROOF OF THE MECHANISM (empirical, 2026-08-07, elevated session):
       The disassembly-derived chain from the investigation was confirmed causally by experiment,
       judged ONLY by a marker file the target program wrote itself, never by Explorer's absence
       (that mistake shipped one wrong fix already, PR #133):

         fDisabledAllowList = 0 (Windows default)  -> test session 7  -> program did NOT run
         fDisabledAllowList = 1                    -> test session 13 -> program RAN
         fDisabledAllowList = 0 (reverted)         -> test session 15 -> program did NOT run

       HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList, and the
       machine has no Applications subkey at all. So the "file not found" in the dialog was always
       the allow-list lookup failing, never the program file. The value was left at its Windows
       default of 0; the app changes it only when the user clicks the button below.

WHAT SHIPPED:
       - gui/app/session_autostart.py (new): the no-administrator route. An HKCU Run value carrying
         "--session-autostart" (a Run value is a COMMAND LINE, unlike the alternate shell, which is
         only an application name - that is why this route needs no AEMSessionShell.exe filename
         trick). Installed on demand and retired as soon as it is claimed, so it exists only while a
         session is actually being started and can never go stale across an update.
       - Self-gating, mandatory because both sessions share one Windows profile and the entry
         therefore fires for the console logon too: SM_REMOTESESSION must be a confirmed yes, and a
         readable console session id may only VETO that, never supply it. main.py runs the claim
         before constructing QApplication, so a console logon shows not even a window flash.
       - A one-shot arm marker written immediately before mstsc launches (background_session.py's
         new before_launch hook, positioned after every refusal the helper can still make),
         consumed on read, rejected when older than 5 minutes or dated in the future. Without it any
         ordinary RDP logon into this account would boot into the macro.
       - rdp_wrapper.initial_program_allow_list_disabled() plus a reversible elevated setter behind
         one UAC prompt (constant-only reg.exe arguments, outcome confirmed by reading the value
         back rather than by trusting a launch result). Deliberately NOT one of the four gating
         setup checks: a background session works fine without it, so it must not disable Start.
       - session_shell.py grew owns_session. As the shell, exiting logs the session off; alongside
         Explorer it does not, so the control window no longer offers "Start Explorer" there and its
         "Sign out" really logs the session off instead of just closing a window.

STILL OPEN, deliberately not done here:
       - The AEMSessionShell.exe launcher and the filename-based mode detection from PR #133 remain
         dead weight (they were built to dodge a CreateProcess quoting problem that does not exist).
         Removing them is filed separately rather than bundled into this fix.
       - Roblox opening via the share link has still never been observed to work, because until now
         nothing ever ran inside that session. It is untested rather than known-good or
         known-broken, and session_shell_log.txt records what the attempt returned.
