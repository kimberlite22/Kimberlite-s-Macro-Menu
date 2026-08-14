; ============================================================
; HELD KEYS ("Key Press" steps)
; ============================================================
; #Include'd into tower_defense_macro_gui.ahk, which splices this in textually: one global
; namespace, so nothing here may redefine a name that file already owns.
;
; Split out for the same reason ocr_matching.ahk is: it can then be loaded and tested WITHOUT
; starting the application (macro/tests/test_held_keys.ahk), which for release logic that has to be
; right under interruption is worth more than keeping the main file whole. Like that file, this one
; borrows from its host and is NOT self-contained - the test supplies stubs for all of it:
;   - LogMsg(), Fmt2(), SafeInt()
;   - ActKeyDown() / ActKeyUp() / ActSend(), the DryRun-aware input primitives
;   - the globals `HeldKeys` (initialized in GLOBAL STATE) and `Running`
; So do NOT /validate this file on its own; validate tower_defense_macro_gui.ahk instead.
;
; A "Key Press" step can keep its key down while the macro carries on with LATER steps, so the
; key-up is not necessarily part of the step that pressed it. Every held key is therefore
; registered here instead of living in a local variable, and every path that can end a screen or a
; run releases the whole registry again.
;
; That safety net is the point of this section, not an extra. A key left logically down in the game
; is the worst thing this feature can produce and, unlike a stray click, it does not resolve itself:
; the game keeps seeing the key as pressed until something sends the matching up event, and by then
; the macro may be long gone. So the release is attached to the STRUCTURE (RunSteps' finally, the
; pause loop, the emergency stop, OnExit) rather than to the individual code paths that end a run,
; which is what makes "did I remember to release it here?" stop being a question a future change has
; to get right.
;
; Three release triggers:
;   - the entry's own one-shot timer, for a plain duration hold that runs asynchronously;
;   - ReleaseHeldKeysForStep, when the step the user picked under "Hold Until" actually finishes;
;   - ReleaseAllHeldKeys, the catch-all above.

; The GUI's own "no target" entry in the Hold Until combo, mirrored here so a config carrying that
; literal text is read as "no target" rather than as a step whose name happens to be it.
HoldUntilNoneChoice() {
    return "(hold duration)"
}

; Normalizes what the user typed into a step's "Key" field into a bare AHK key name, so both
; "{Space}" and "Space" arrive as "Space". Returns "" for anything unusable, which the caller
; reports - sending a malformed "{ down}" would otherwise do nothing at all, silently.
NormalizeHoldKeyName(raw) {
    key := Trim(raw)
    ; The AHK notation gets copied out of the docs at least as often as the bare name gets typed.
    key := Trim(RegExReplace(key, "^\{(.*)\}$", "$1"))
    ; A key name is a single token. Anything with whitespace inside is a key SEQUENCE, which this
    ; step deliberately does not support: a sequence cannot be held down as a unit.
    if (key = "" || RegExMatch(key, "\s"))
        return ""
    return key
}

; Short human name for a step, for log lines that have to point at another step.
StepShortName(st) {
    return Trim(st.Label) != "" ? Trim(st.Label) : st.Type
}

; Presses `key` down and registers it as held. `untilStepIdx` is the 1-based index of the step whose
; completion releases it (0 = no step target). `deadlineMs` is an upper bound in milliseconds, 0 for
; none. Returns the entry, so a synchronous hold can release exactly the one it created.
HoldKeyDown(key, desc, untilStepIdx := 0, deadlineMs := 0) {
    global HeldKeys, Paused
    ; The game has ONE state per key, so holding a key that is already held is not a second hold:
    ; whichever release ran first would end both, and the other one's release would then send a
    ; stray key-up for a key nobody is holding. The older hold is ended here and replaced.
    ReleaseHeldKeysForKey(key, "replaced by a new hold")
    ; Registering and pressing must be one indivisible act. Escape runs on its own thread and calls
    ; ReleaseAllHeldKeys; landing between the two would let it release an entry whose key-down has
    ; not been sent yet, after which this thread presses a key that is no longer registered and
    ; nothing is left to ever release it. Critical defers that hotkey by the length of one key-down.
    entry := {Key: key, Desc: desc, UntilStepIdx: untilStepIdx, Released: false, Timer: ""}
    prevCritical := A_IsCritical
    Critical
    try {
        ; Asking about the pause HERE, inside the same indivisible section as the press, is what
        ; makes "is it paused?" and "press it" one decision. A pause landing after the step loop's
        ; own check but before this line has already swept an empty registry, so a key pressed
        ; afterwards would stay down for the whole pause, and a "Hold Until" hold has no deadline to
        ; end it. Reported as released because nothing was ever pressed.
        if Paused {
            entry.Released := true
            LogMsg("Key press skipped: paused.")
            return entry
        }
        HeldKeys.Push(entry)
        ActKeyDown(key)
        if (deadlineMs > 0) {
            ; A negative period makes this one-shot. The timer thread does nothing but the key-up
            ; and its own bookkeeping, deliberately: it can interrupt the main thread in the middle
            ; of another Send, and a single key-up is the smallest thing that can interleave there.
            entry.Timer := ReleaseHeldKeyEntry.Bind(entry, "hold time elapsed")
            SetTimer entry.Timer, -deadlineMs
        }
    } finally {
        Critical prevCritical
    }
    return entry
}

; Releases one registered entry, exactly once. This is the ONLY place a held key comes back up, so
; the same entry can safely be handed to it by both the release timer and the catch-all path:
; whichever runs first wins and the other is a no-op.
;
; `Critical` is what makes that true, by closing the window between the Released check and the
; assignment - the timer could otherwise interrupt exactly there and send a second key-up. It is
; saved and restored rather than simply switched on, because Critical belongs to the whole THREAD
; and is NOT undone by returning from a function: leaving it on would silently suspend every other
; timer (the local bridge's poll among them) for the rest of the run.
ReleaseHeldKeyEntry(entry, reason) {
    global HeldKeys
    prevCritical := A_IsCritical
    Critical
    try {
        if entry.Released
            return
        entry.Released := true
        if (entry.Timer != "") {
            SetTimer entry.Timer, 0
            entry.Timer := ""
        }
        ActKeyUp(entry.Key)
        for index, held in HeldKeys {
            if (held = entry) {
                HeldKeys.RemoveAt(index)
                break
            }
        }
    } finally {
        Critical prevCritical
    }
    LogMsg("Released " entry.Desc " (" reason ").")
}

; Releases every held key. The safety net described at the top of this section.
ReleaseAllHeldKeys(reason := "released") {
    global HeldKeys
    ; Over a snapshot, not the live array: a release timer firing mid-loop removes its own entry,
    ; which would shift the remaining ones out from under an index walk. ReleaseHeldKeyEntry is
    ; idempotent, so an entry the timer got to first is simply skipped here.
    for entry in HeldKeys.Clone()
        ReleaseHeldKeyEntry(entry, reason)
}

; Releases the keys bound to the step that just finished, identified by its 1-based index in the
; screen's step list. Snapshot for the same reason as above.
ReleaseHeldKeysForStep(stepIdx) {
    global HeldKeys
    for entry in HeldKeys.Clone() {
        if (entry.UntilStepIdx = stepIdx)
            ReleaseHeldKeyEntry(entry, "step " stepIdx " finished")
    }
}

; Releases any hold of one particular key. AHK's `=` compares strings case-insensitively, which is
; what key names want ("space" and "Space" are the same key).
ReleaseHeldKeysForKey(key, reason) {
    global HeldKeys
    for entry in HeldKeys.Clone() {
        if (entry.Key = key)
            ReleaseHeldKeyEntry(entry, reason)
    }
}

; Resolves a step's "Hold Until" selection to a 1-based index in `steps`, or 0 when nothing matches.
; The GUI stores the combo's own display text ("3. Click Button"), which carries BOTH halves on
; purpose: steps have no stable identity of their own, so the name is what survives the user
; reordering the screen, and the number is what still identifies a step whose Name field is empty.
ResolveHoldUntilStepIndex(steps, raw, selfIdx) {
    label := Trim(raw)
    if (label = "" || label = HoldUntilNoneChoice())
        return 0
    idx := 0
    name := label
    if RegExMatch(label, "^(\d+)\.\s*(.*)$", &m) {
        idx := Integer(m[1])
        name := Trim(m[2])
    }
    ; A step with that exact Name first: that is the half a reorder cannot invalidate.
    if (name != "") {
        for i, st in steps {
            if (i != selfIdx && Trim(st.Label) != "" && StrLower(Trim(st.Label)) = StrLower(name))
                return i
        }
    }
    ; Otherwise the recorded position, which is all an unnamed step ever had.
    if (idx >= 1 && idx <= steps.Length && idx != selfIdx)
        return idx
    return 0
}

; Sleeps out a synchronous hold without going deaf to a stop. Deliberately NOT
; WaitSecondsInterruptible: that one logs a countdown line every 250ms, which for the sub-second
; holds this step is normally used for would be far more log than action.
HoldWaitInterruptible(ms) {
    global Running, Paused
    endTick := A_TickCount + ms
    ; Paused ends the wait as well as Running: SetPaused() has already released the key by then, so
    ; sitting out the rest of a hold that is over serves nothing.
    while (Running && !Paused) {
        remaining := endTick - A_TickCount
        if (remaining <= 0)
            return
        Sleep (remaining < 50 ? remaining : 50)
    }
}

; Runs one "Key Press" step. Three shapes, decided by the step's own fields:
;   - no hold time and no target: a plain tap, exactly like any other Send.
;   - a hold time: press, wait it out, release. Unless "Go to next step while holding" is on, in
;     which case the entry's one-shot timer does the release and this returns immediately.
;   - a "Hold Until" target: press and return immediately; the step loop releases the key once that
;     target step finishes. Always asynchronous, since the step that ends the hold is a later one
;     and could never run if this blocked. A hold time then acts as an upper bound instead.
RunKeyPressStep(step, steps, stepIdx) {
    keyName := NormalizeHoldKeyName(step.Key)
    if (keyName = "") {
        LogMsg("Key Press skipped: " (Trim(step.Key) = ""
            ? "no key set."
            : "'" Trim(step.Key) "' is not a single key name."))
        return
    }
    what := "key '" keyName "'" (step.Label != "" ? " (" step.Label ")" : "")
    holdMs := Max(0, SafeInt(step.HoldMs))
    untilRaw := Trim(step.HoldUntilStep)
    untilIdx := ResolveHoldUntilStepIndex(steps, untilRaw, stepIdx)
    if (untilIdx = 0 && untilRaw != "" && untilRaw != HoldUntilNoneChoice())
        LogMsg("Key Press: 'Hold Until' target '" untilRaw "' is not a step of this screen - using the hold time instead.")

    if (untilIdx > 0) {
        ; An entry that comes back already released was never pressed (a pause landed on it), so
        ; there is no hold to announce.
        if HoldKeyDown(keyName, what, untilIdx, holdMs).Released
            return
        LogMsg("Holding " what " until step " untilIdx " (" StepShortName(steps[untilIdx]) ") finishes"
            (holdMs > 0 ? ", at most " Fmt2(holdMs / 1000) "s" : "") ".")
        if (untilIdx < stepIdx)
            LogMsg("  That step sits before this one, so the hold ends when this screen does.")
        return
    }
    if (holdMs <= 0) {
        ActSend("{" keyName "}")
        LogMsg("Pressed " what ".")
        return
    }
    if step.HoldAsync {
        if HoldKeyDown(keyName, what, 0, holdMs).Released
            return
        LogMsg("Holding " what " for " Fmt2(holdMs / 1000) "s while the macro continues.")
        return
    }
    entry := HoldKeyDown(keyName, what, 0, 0)
    if entry.Released
        return
    LogMsg("Holding " what " for " Fmt2(holdMs / 1000) "s...")
    HoldWaitInterruptible(holdMs)
    ReleaseHeldKeyEntry(entry, "hold time elapsed")
}
