Title: solange die application offen ist kann man esc nicht mehr benutzen in anderen programmen.
       Mach das weg
Prio:  1

Goal:  Pressing Escape while any other application is focused reaches that application normally.
       The engine only takes over the Escape key as an emergency-stop/cancel while it actually has
       something to cancel or stop (an active region/field capture, an active overlay/pin, or a
       running macro); otherwise the keypress passes through untouched.
Files: macro/tower_defense_macro_gui.ahk: the bare `Escape::` hotkey (~4451-4492) and the globals
       it reads (RegionCapActive, FieldCaptureId, CaptureTarget, OverlayVisible, LockedProcess,
       Running).
Steps: 1. Confirmed root cause: `Escape::` is a plain, unconditional AHK hotkey with no `#HotIf`
          guard, so AHK claims and swallows every Escape press system-wide the whole time the
          engine is running, whether or not there is anything to cancel or stop. The engine runs
          hidden from startup (see "Python GUI" in CLAUDE.md), so in practice this is nearly always.
       2. Add a `#HotIf` guard (a small predicate function referencing RegionCapActive,
          FieldCaptureId, CaptureTarget, OverlayVisible, LockedProcess, Running) above the
          `Escape::` hotkey so it is only registered/active while at least one of those is true;
          otherwise AHK does not claim the key at all and it reaches whatever window has focus.
       3. Keep the hotkey body itself unchanged: existing priority order (capture-cancel before
          stop) and the StopRequested latch must behave exactly as today whenever the guard lets it
          fire.
       4. Since running the app is off-limits per CLAUDE.md, verify this only by reading the code
          (confirm the `#HotIf` predicate's truth table matches every branch inside the hotkey
          body) rather than launching the macro; ask the user to confirm behavior live if in doubt.
Open:  -
