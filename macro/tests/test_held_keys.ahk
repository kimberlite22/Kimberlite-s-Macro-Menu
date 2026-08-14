#Requires AutoHotkey v2.0
#SingleInstance Off
#Warn All, Off

; Tests for the held-key registry behind the "Key Press" step (macro/held_keys.ahk).
;
; Why this exists: this is the one part of the engine whose failure mode is a key left logically
; DOWN in the game, which nothing resolves on its own. The release paths it has to get right are
; also the ones that are hardest to judge by reading, because a one-shot timer can interrupt the
; main thread between any two lines. So the properties below are asserted rather than argued:
; a release happens exactly once per press, a cancelled timer never sends a second key-up, and
; Critical is left exactly as it was found (leaving it on would silently suspend every other timer
; in the app for the rest of the run).
;
; Run it:
;     "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe" macro\tests\test_held_keys.ahk [outfile]
; Exit code is the number of failures, so a caller can gate on it. With an outfile argument the
; per-case report is written there as well (AutoHotkey64.exe is a GUI subsystem binary, so its
; stdout is only usable when the caller redirects it).
;
; NOT wired into .github/workflows/ci.yml: that runner has no AutoHotkey and installing one is its
; own decision. Run it locally after touching held_keys.ahk.

#Include ..\held_keys.ahk

; --- Stubs for everything held_keys.ahk borrows from the main script -----------------------------
; KeyEvents records what would have gone to the game, which is what most cases below assert on.

global HeldKeys := []
global Running := true
global Paused := false
global KeyEvents := []
global LogLines := []

ActKeyDown(key) {
    global KeyEvents
    KeyEvents.Push("down:" key)
}
ActKeyUp(key) {
    global KeyEvents
    KeyEvents.Push("up:" key)
}
ActSend(keys) {
    global KeyEvents
    KeyEvents.Push("send:" keys)
}
LogMsg(msg) {
    global LogLines
    LogLines.Push(msg)
}

; Copied verbatim from tower_defense_macro_gui.ahk so the stubs cannot drift into being more
; forgiving than the real things.
Fmt2(n) {
    return Format("{:.2f}", n + 0)
}
SafeInt(val, def := 0) {
    s := Trim(String(val))
    if (s = "")
        return def
    s := StrReplace(s, ",", ".")
    try return Integer(Round(Number(s)))
    return def
}

; --- Tiny assert harness -------------------------------------------------------------------------

global Failures := 0
global Report := ""

Check(label, got, want) {
    global Failures, Report
    ok := (String(got) = String(want))
    if !ok
        Failures += 1
    Report .= (ok ? "PASS  " : "FAIL  ") label
        . (ok ? "" : "   (got " (got = "" ? "<empty>" : got) ", want " (want = "" ? "<empty>" : want) ")")
        . "`n"
}

; Resets everything a case can dirty, so cases stay independent of their order.
Reset() {
    global HeldKeys, KeyEvents, LogLines, Running, Paused
    HeldKeys := []
    KeyEvents := []
    LogLines := []
    Running := true
    Paused := false
}

Events() {
    global KeyEvents
    out := ""
    for value in KeyEvents
        out .= (out = "" ? "" : ",") value
    return out
}

; 1 when any log line contains `needle`, 0 otherwise. Not InStr() directly: AHK's `&&` yields the
; operand rather than a boolean, so a raw InStr result would be compared as a character position.
LoggedSubstring(needle) {
    global LogLines
    for line in LogLines {
        if InStr(line, needle)
            return 1
    }
    return 0
}

Step(type, label := "", key := "", holdMs := "0", holdAsync := 0, holdUntil := "") {
    return {Type: type, Label: label, Key: key, HoldMs: holdMs, HoldAsync: holdAsync,
        HoldUntilStep: holdUntil}
}

; --- The key name field ---------------------------------------------------------------------------

Check("a bare key name passes through", NormalizeHoldKeyName("e"), "e")
Check("AHK brace notation is accepted too", NormalizeHoldKeyName("{Space}"), "Space")
Check("surrounding whitespace is trimmed", NormalizeHoldKeyName("  F1  "), "F1")
Check("an empty field is rejected", NormalizeHoldKeyName("   "), "")
; A sequence cannot be held down as a unit, so it is refused rather than sent as a malformed
; "{a b down}" that would silently do nothing.
Check("a key sequence is rejected", NormalizeHoldKeyName("a b"), "")

; --- Press and release ----------------------------------------------------------------------------

Reset()
criticalBefore := A_IsCritical
entry := HoldKeyDown("e", "key 'e'")
Check("a press registers the key", HeldKeys.Length, 1)
ReleaseHeldKeyEntry(entry, "test")
Check("press then release is exactly one down and one up", Events(), "down:e,up:e")
Check("a released entry leaves the registry", HeldKeys.Length, 0)
; Critical belongs to the THREAD, not to the function, so a release that switched it on without
; putting it back would suspend every other timer in the app for the rest of the run.
Check("Critical is left as it was found", A_IsCritical, criticalBefore)

Reset()
entry := HoldKeyDown("e", "key 'e'")
ReleaseHeldKeyEntry(entry, "first")
KeyEvents := []
ReleaseHeldKeyEntry(entry, "second")
Check("releasing the same entry twice is a no-op", Events(), "")

; --- Holding a key that is already held ------------------------------------------------------------
; The game has one state per key, so this is a replacement, not a second hold. Without that, either
; release would end both and the loser's own release would send a key-up for a key nobody holds.

Reset()
first := HoldKeyDown("e", "key 'e' (first)", 0, 60000)
second := HoldKeyDown("e", "key 'e' (second)", 4)
Check("a second hold of the same key replaces the first", Events(), "down:e,up:e,down:e")
Check("and only one entry is left", HeldKeys.Length, 1)
Check("which is the new one", HeldKeys[1].UntilStepIdx, 4)
KeyEvents := []
ReleaseHeldKeyEntry(first, "late")
Check("the replaced hold can no longer release the key", Events(), "")
ReleaseAllHeldKeys()

Reset()
; A different key is a genuinely separate hold and must not disturb the first.
HoldKeyDown("a", "key 'a'")
HoldKeyDown("b", "key 'b'")
Check("a different key is left alone", Events(), "down:a,down:b")
Check("and both stay registered", HeldKeys.Length, 2)
ReleaseAllHeldKeys()

; --- The catch-all -------------------------------------------------------------------------------

Reset()
HoldKeyDown("a", "key 'a'")
HoldKeyDown("b", "key 'b'", 3)
HoldKeyDown("c", "key 'c'", 0, 60000)
ReleaseAllHeldKeys("screen ended")
Check("release-all releases every key", Events(), "down:a,down:b,down:c,up:a,up:b,up:c")
Check("release-all empties the registry", HeldKeys.Length, 0)

; --- Releasing on a target step's completion ------------------------------------------------------

Reset()
HoldKeyDown("q", "key 'q'", 2)
HoldKeyDown("w", "key 'w'", 5)
HoldKeyDown("r", "key 'r'", 2)
ReleaseHeldKeysForStep(2)
Check("only the keys bound to that step are released", Events(), "down:q,down:w,down:r,up:q,up:r")
Check("a hold bound to a later step survives", HeldKeys.Length, 1)
Check("and it is the right one", HeldKeys[1].Key, "w")

; --- The deadline timer ----------------------------------------------------------------------------

Reset()
HoldKeyDown("z", "key 'z'", 0, 120)
Check("the key is down before the deadline", Events(), "down:z")
Sleep 400
Check("the deadline timer releases the key", Events(), "down:z,up:z")
Check("and deregisters it", HeldKeys.Length, 0)

Reset()
entry := HoldKeyDown("x", "key 'x'", 0, 150)
ReleaseHeldKeyEntry(entry, "released early")
Sleep 400
Check("an early release cancels the timer", Events(), "down:x,up:x")

; --- Resolving a "Hold Until" target ---------------------------------------------------------------
; The stored text is the step editor's own combo entry, "<position>. <name>". Both halves matter:
; the name survives a reorder, the position is all an unnamed step ever had.

steps := [Step("Button Click", "Click Button"), Step("Key Press", "", "e"), Step("Wait")]
Check("no target resolves to nothing", ResolveHoldUntilStepIndex(steps, "", 2), 0)
Check("the none choice resolves to nothing", ResolveHoldUntilStepIndex(steps, "(hold duration)", 2), 0)
Check("a named target resolves", ResolveHoldUntilStepIndex(steps, "1. Click Button", 2), 1)
moved := [Step("Wait"), Step("Key Press", "", "e"), Step("Button Click", "Click Button")]
Check("a reorder is survived by the name half", ResolveHoldUntilStepIndex(moved, "1. Click Button", 2), 3)
Check("an unnamed target resolves by position", ResolveHoldUntilStepIndex(steps, "3. Wait", 2), 3)
Check("a target that no longer exists resolves to nothing", ResolveHoldUntilStepIndex(steps, "9. Gone", 2), 0)
; It is the step doing the pressing, so its own completion could only ever come after the release.
Check("a step cannot wait for itself", ResolveHoldUntilStepIndex(steps, "2. Key Press", 2), 0)

; --- The step itself -------------------------------------------------------------------------------

Reset()
RunKeyPressStep(Step("Key Press", "", ""), [], 1)
Check("a step with no key does nothing at all", Events(), "")
Check("and says so", LoggedSubstring("no key set"), 1)

Reset()
RunKeyPressStep(Step("Key Press", "", "e"), [], 1)
Check("no hold time is a plain tap, not a down/up pair", Events(), "send:{e}")

Reset()
RunKeyPressStep(Step("Key Press", "", "e", "120"), [], 1)
Check("a hold time without async blocks and releases", Events(), "down:e,up:e")
Check("and nothing is left held", HeldKeys.Length, 0)

Reset()
RunKeyPressStep(Step("Key Press", "", "e", "60000", 1), [], 1)
Check("an async hold returns with the key still down", Events(), "down:e")
Check("and the key stays registered for a later release", HeldKeys.Length, 1)
ReleaseAllHeldKeys()

Reset()
target := [Step("Key Press", "", "e", "0", 0, "2. Click Button"), Step("Button Click", "Click Button")]
RunKeyPressStep(target[1], target, 1)
Check("a hold-until target returns immediately with the key down", Events(), "down:e")
Check("bound to that target step", HeldKeys[1].UntilStepIdx, 2)
ReleaseHeldKeysForStep(1)
Check("an unrelated step finishing does not release it", Events(), "down:e")
ReleaseHeldKeysForStep(2)
Check("the target step finishing does", Events(), "down:e,up:e")

Reset()
; A target that cannot be resolved must not silently become an unbounded hold: it degrades to the
; step's own hold time, which is the behavior the user can still see and correct.
RunKeyPressStep(Step("Key Press", "", "e", "120", 0, "9. Gone"), [Step("Wait")], 1)
Check("an unresolvable target falls back to the hold time", Events(), "down:e,up:e")
Check("and reports why", LoggedSubstring("not a step of this screen"), 1)

Reset()
; A stop landing mid-hold must not sit out the rest of it. Running is what HoldWaitInterruptible
; watches, and the release still has to happen.
Running := false
RunKeyPressStep(Step("Key Press", "", "e", "60000"), [], 1)
Check("a stop cuts a synchronous hold short and still releases", Events(), "down:e,up:e")

Reset()
; A pause arriving DURING a synchronous hold: SetPaused() releases the key, and the wait must not
; then sit out the remaining minute. Simulated by pausing from the stub the wait keeps calling.
holdEntry := HoldKeyDown("e", "key 'e'")
Paused := true
ReleaseAllHeldKeys("paused")
HoldWaitInterruptible(60000)
Check("a pause ends a hold that is already running", Events(), "down:e,up:e")
Paused := false

Reset()
; A pause landing after the step loop's own check but before the press: SetPaused() has already
; swept an empty registry, so pressing now would leave the key down for the whole pause, and a
; "Hold Until" hold has no deadline to end it. Nothing may be pressed at all.
Paused := true
RunKeyPressStep(Step("Key Press", "", "e", "0", 0, "2. Click Button"),
    [Step("Key Press"), Step("Button Click", "Click Button")], 1)
Check("a pause racing the press means nothing is pressed", Events(), "")
Check("and nothing is registered", HeldKeys.Length, 0)
Check("and it says why", LoggedSubstring("skipped: paused"), 1)

Reset()
Paused := true
RunKeyPressStep(Step("Key Press", "", "e", "60000"), [], 1)
Check("the same holds for a synchronous hold", Events(), "")
Paused := false

; --- Report ----------------------------------------------------------------------------------------

total := StrSplit(Trim(Report, "`n"), "`n").Length
summary := Report "`n" (Failures = 0 ? "OK" : "FAILED") ": " (total - Failures) "/" total " passed`n"
if (A_Args.Length >= 1)
    FileAppend(summary, A_Args[1], "UTF-8-RAW")
try FileAppend(summary, "*")
ExitApp(Failures)
