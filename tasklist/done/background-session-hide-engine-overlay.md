Title: Die ingame macro gui mit grauen hintergrund und so weiter verschwindet komplett (nur wenn man
       über session startet) und es bleibt einfach nur das roblox fenster offen.
Completed: 2026-08-07
Commit:    -

Result: The engine now resolves once at startup whether its own Windows session is the physical
console session (ProcessIdToSessionId against WTSGetActiveConsoleSessionId, both kernel32) and
skips CreateOverlay() entirely when it is not, so a background RDP session shows nothing but the
Roblox window. CreateOverlay() turned out to be the single choke point for every overlay window
there is (the four gray bars, the Log panel, the Time Breakdown panel and the Application Stats
panel), so one early return covers all of them; the window lock is kept because it repositions the
game window and draws nothing. The suppressed case leaves OverlayVisible false, which the existing
code already handles: CloseOverlay's hadOverlay ternary words its log line for it, every
Render*Panel() returns early on an empty control, and Escape still latches onto Running /
LockedProcess. Fails closed in both directions: a failed session read, or no session attached to
the console, keeps today's overlay, and the DllCall block uses "catch Any" rather than a bare
"catch" so a non-Error throw cannot take startup down over a cosmetic decision. Verified without
launching the app (CLAUDE.md hard rule) by AutoHotkey64.exe /validate /ErrorStdOut, first
confirming on a deliberately broken script that /validate really does report parse errors. Known
scope note: the condition is "not the physical console session", so a user who runs the whole app
over an ordinary Remote Desktop connection also loses the overlay. That is the same situation the
condition is meant to describe (nobody is looking at that desktop locally) and it is the only
engine-side signal that needs no protocol change, but it is a real behavior change for that setup.
