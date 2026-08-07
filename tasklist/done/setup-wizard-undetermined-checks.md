Title:     the last point on the checklist is not ok altough the remote connection worked flawlessly
Completed: 2026-08-07
Commit:    -

Result: A Background Session setup check that cannot DETERMINE its answer no longer disables Start.
CheckResult gained an "undetermined" flag, set in exactly the four branches that already reported
"could not be read", and SetupStatus gained "can_start" (no check is a genuine negative) and
"undetermined". The tab gates Start on can_start instead of ok and renders three states, the middle
one carrying the warning the user asked for: "Setup: could not be fully confirmed. Start is enabled
anyway. Only start with warnings if you know what you are doing." Detail lines are prefixed OK,
Warning or Needs attention. A value that WAS read and is wrong still blocks Start, unchanged.

The Windows build check also stopped being silent about the two different version numbers Windows
reports for termsrv.dll. New termsrv_string_version() reads the StringFileInfo FileVersion
(resolving language and codepage through VarFileInfo\Translation rather than hardcoding 040904B0,
and normalising both the "10.0.26100.8875 (WinBuild.160101.0800)" and comma-separated forms). It is
deliberately DIAGNOSTIC ONLY: an intermediate version of this change let a section matching either
number pass, which review caught as a false-pass risk, because RDP Wrapper builds its rdpwrap.ini
lookup key exclusively from VS_FIXEDFILEINFO. That was confirmed empirically on the reporting
machine rather than taken on faith: binary 10.0.26100.4484, string 10.0.26100.8875, an rdpwrap.ini
containing [10.0.26100.4484] but not [10.0.26100.8875], and a working RDP Wrapper, which is only
possible if the binary version is the key. The binary version is therefore the sole matching key,
and the string version only makes the messages more useful, mentioned only when the two differ.

Root cause of the original report: NOT FOUND, and deliberately not guessed at. The reported failure
("The fixed binary version of Windows termsrv.dll could not be read") could not be reproduced
afterwards on the same machine, at the same commit, from source and from a faithful frozen build
with Qt bundled, all of which return ok. Ruled out with evidence: WOW64 file system redirection (the
exe is x64 and termsrv.dll exists only in System32), a lost SystemRoot on the self-install relaunch
(no env= anywhere, the environment is inherited), the bundled VERSION data file shadowing
version.dll (GetModuleFileNameW shows it still resolving to C:\WINDOWS\SYSTEM32\VERSION.dll when
frozen), a later code change (the user's build postdates the file's only commit), and a pending
Windows update (no CBS or WU reboot flag, termsrv.dll untouched since 2025-07-23). The best
remaining theory, unproven and NOT acted on, is a transient read block on the first launch of a
freshly built unsigned exe. This task therefore fixes the consequence, which is wrong on its own
terms: a detection gap must never disable a feature the user has already demonstrated works.

Verified with the full gui/ pytest suite (399 passed) and by running the real check_setup() against
the live machine, both normally (all four OK) and with termsrv_binary_version forced to None to
reproduce the user's exact failure, which now yields can_start=True with a Warning line instead of
a disabled Start button. gui.exe was never launched, per CLAUDE.md.
