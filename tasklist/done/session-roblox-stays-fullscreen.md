Title: Roblox soll in der session in full screen starten und auch bleiben fuer immer. Das macro soll
       nicht resizen wenn es in der session gestartet wird

Completed: 2026-08-08
Commit:    -

Result: Roblox is made full screen by Roblox, not by the macro. All four of the task's open
questions were answerable from evidence rather than by trying it. Roblox does remember its own
window state per Windows user, in %LOCALAPPDATA%\Roblox\GlobalBasicSettings_13.xml (Fullscreen, next
to StartScreenSize and StartScreenPosition), and a background session runs as that same user, so it
inherits it. That also settles whether ticking it once is enough: it is not, because Roblox rewrites
the whole file when it exits, so one windowed round on the physical desktop puts it straight back
and the setting has to be asserted. Asserting it as a borderless window built by WinMove is exactly
the resizing the task forbids, so the remaining answer is Roblox' own fullscreen mode, which
roblox-fullscreen-opening had rejected only because it would fight the window lock: that objection
is gone here precisely because this task removes the lock. New gui/app/roblox_display.py therefore
writes that one boolean before the session starts Roblox (gui/app/session_shell.py, on both the
start-up path and the control window's Start Roblox button, since a client closed inside the session
has already rewritten the file). It is the narrowest possible edit to a file that belongs to another
application and holds every preference the user has: one element, matched not parsed, only when it
is currently false, line endings carried through, written through tempfile.mkstemp plus os.replace,
and any file that does not hold exactly one such element left completely alone. The engine side is
LeaveGameWindowGeometryAlone() = InBackgroundWindowsSession && FullscreenOpeningEnabled(). Both
halves are load-bearing: clicks are percentages OF THE OPENING, so the engine may only stop
asserting the window's rectangle once the rectangle the game produces by itself already is that
opening, which is true only while the opening is the whole screen. That is policy, not the decision:
the two halves live in different processes and the Python one can fail silently, so ForceGameWindow
also MEASURES the window (GameWindowFillsOpening, visible edges against the opening within 2px) and
falls back to the old positioning and lock when it does not fill it, logging why. Activation stays
unconditional, since focus is input rather than geometry, and LockedProcess is still claimed either
way because ReactivateGameWindow and the Escape guard read it; only the twice-a-second snap-back is
skipped. WinRestore turned out to be a resize in disguise (it un-maximizes) and now only runs on a
minimized window there, with the unconditional restore re-added on the fallback path so it stays
equivalent to the old behavior. Whether the lock runs is started AND stopped at the one place the
decision is made, which also covers a disconnect or preset-switch restart that reaches
ForceGameWindow without CloseOverlay in between; EnforceWindowLock deliberately does not guard on
the reporting flag, because Pin is also a ForceGameWindow attempt and would otherwise switch a
running lock off by finding the window filling the opening that same run had put it in. Pin and the
local bridge's FORCE_GAME_WINDOW keep working as a manual override rather than becoming no-ops, and
say which of the two things they did. Deliberately NOT done: anything watching the window
afterwards. Re-checking on a timer is what the lock was, and every restart the engine already
performs takes the measurement again. Known trade-off, called out for review: the Roblox setting is
shared with the physical desktop, so the next Roblox there also opens full screen until F11 puts it
back. Verified without launching the app (CLAUDE.md hard rule) by AutoHotkey64.exe /validate, first
confirming on a deliberately broken copy that it really does report parse errors (exit 2), and by
the Python suite (559 passed, including 11 new tests for the settings rewrite and 5 for the gate).
