; ============================================================
; REMOTE BRIDGE (Phase 0a) - local, network-free control interface for a future companion agent
; ============================================================
; A file-based bridge so an external, out-of-process "agent" (added in a later phase) can watch the
; macro and issue a SMALL, fixed set of safe commands - WITHOUT any networking code living inside
; this AutoHotkey app. It deliberately mirrors the OCR helper's file protocol (see EnsureOcrServer /
; RunOcrOnRegion): plain files next to this script, atomic publish via a .tmp + FileMove, and a
; request token so a stale file is never mistaken for a fresh one.
;
; SECURITY MODEL (read this before extending):
;   * The command channel is UNTRUSTED input. It can ONLY trigger the fixed whitelist in
;     RemoteBridgeApplyCommand - never raw coordinates, keystrokes, scripts, or arbitrary preset
;     data. Every argument is validated against existing state (e.g. a preset name must already
;     exist via PresetIndex) before it is acted on.
;   * Off by default. Nothing is written or read unless [General] RemoteBridgeEnabled = 1, so the
;     remote-control surface only exists once the user knowingly opts in.
;   * Every command maps onto the SAME mechanism a local hotkey/button already uses (Paused, Running,
;     ActivePresetName, or a preset the run loop switches to at a cycle boundary), so a remote command
;     can never do more than a local key press or button click.
;
; FILES (all in DataDir, alongside the ocr_*.txt protocol files):
;   remote_status.json - written by the macro (~1x/sec) : a JSON snapshot of run state for the
;                        agent. The "timestamp" field doubles as a heartbeat - a consumer treats a
;                        stale timestamp as "macro offline" (nothing is written after a crash/exit).
;   remote_cmd.txt     - written by the agent, consumed (DELETED) by the macro : one command, format
;                        <token>|<TYPE>|<arg>   (arg optional). The writer must atomic-publish it
;                        (write <file>.tmp, then move over remote_cmd.txt) so the macro never reads
;                        a half-written command. Deleting on read makes every command run at most once.
;   remote_ack.txt     - written by the macro after handling a command :  <token>|<ok|error>|<message>
;                        so the agent can confirm the command applied (or learn why it was rejected).
;
; NOTE ON LOGS: the agent reads the human log straight from macro_log.txt (it can tail that file),
; so the status snapshot deliberately does NOT duplicate log lines.

RemoteBridgeLastStatusTick := 0     ; A_TickCount of the last status snapshot (throttles writes to ~1/sec)
RemoteBridgeLastCmdToken := ""      ; token of the last command handled, to ignore a re-published duplicate

; True only while [General] RemoteBridgeEnabled = 1 in config.ini - read fresh every call, exactly
; like CheckDisconnectTick reads [General] DisconnectEnabled, so a checkbox toggled and saved in the
; Python GUI takes effect on this engine's very next tick without a restart.
RemoteBridgeIsEnabled() {
    return SafeInt(Cfg("General", "RemoteBridgeEnabled", 0)) ? true : false
}

; Runs on a timer the whole time the app is up: consumes a pending command (if any), then refreshes
; the status snapshot at most ~1x/second. A no-op (and writes nothing) while the bridge is disabled.
; AHK never re-enters a running timer, so no busy-guard is needed here.
RemoteBridgeTick() {
    global RemoteBridgeLastStatusTick
    if !RemoteBridgeIsEnabled()
        return
    RemoteBridgeProcessCommand()
    if (A_TickCount - RemoteBridgeLastStatusTick >= 1000) {
        RemoteBridgeWriteStatus()
        RemoteBridgeLastStatusTick := A_TickCount
    }
}

; Reads and consumes remote_cmd.txt (if present), applies the (whitelisted) command, and writes an
; ack. Consuming (deleting) the file first guarantees a command runs at most once even if applying
; it below raises. A FileRead that fails (e.g. the writer is mid-publish without an atomic move) is
; swallowed and simply retried on the next tick.
RemoteBridgeProcessCommand() {
    global RemoteBridgeLastStatusTick, RemoteBridgeLastCmdToken, DataDir
    cmdFile := DataDir "\remote_cmd.txt"
    if !FileExist(cmdFile)
        return

    raw := ""
    try raw := FileRead(cmdFile, "UTF-8")
    catch
        return
    try FileDelete cmdFile      ; consume immediately -> at-most-once execution

    raw := Trim(raw, " `t`r`n")
    if (raw = "")
        return

    parts := StrSplit(raw, "|")
    token := (parts.Length >= 1) ? Trim(parts[1]) : ""
    verb  := (parts.Length >= 2) ? Trim(parts[2]) : ""
    arg   := (parts.Length >= 3) ? Trim(parts[3]) : ""

    ; A repeated token means the writer re-published the same command (e.g. a retry before it saw the
    ; ack) - acknowledge it again but don't act on it twice. Tokenless commands (manual testing) skip
    ; this and always run; delete-on-read already caps them at once per file.
    if (token != "" && token = RemoteBridgeLastCmdToken) {
        RemoteBridgeWriteAck(token, {ok: true, msg: "Duplicate ignored."})
        return
    }
    if (token != "")
        RemoteBridgeLastCmdToken := token

    try result := RemoteBridgeApplyCommand(verb, arg)
    catch Any as err
        result := {ok: false, msg: LocalBridgeCommandErrorMessage(err)}
    RemoteBridgeWriteAck(token, result)

    ; Push a fresh snapshot right after a state-changing command so the agent sees the effect at once,
    ; instead of waiting up to a second for the next scheduled status write.
    RemoteBridgeWriteStatus()
    RemoteBridgeLastStatusTick := A_TickCount
}

; The command whitelist. Returns {ok, msg}. This is the ONLY place a remote command turns into an
; action - every branch validates its input and maps onto an existing local mechanism. Do NOT add a
; branch that accepts raw coordinates/keys/steps here (see the security model at the top).
RemoteBridgeApplyCommand(verb, arg) {
    global Running, Paused, ActivePresetName, ConfigFile, PendingPresetSwitch, PresetSwitchRestartPending, StopRequested, MacroActive
    switch verb {
        case "PAUSE":
            if !Running
                return {ok: false, msg: "Not running."}
            SetPaused(true)         ; same effect as the F9 hotkey, held keys released included
            LogMsg("Remote: paused.")
            return {ok: true, msg: "Paused."}

        case "RESUME":
            if !Running
                return {ok: false, msg: "Not running."}
            SetPaused(false)        ; same effect as the F9 hotkey
            LogMsg("Remote: resumed.")
            return {ok: true, msg: "Resumed."}

        case "STOP":
            ; Latch a stop request and cancel any queued/committed preset switch FIRST, unconditionally.
            ; StopRequested aborts a restart that is mid-flight (Running already false, StartMacro between
            ; MainLoop returning and re-setting Running:=true - e.g. during ForceGameWindow's Sleep);
            ; clearing the queue keeps a STOP from being mistaken for a switch and keeps the status
            ; written right after this from showing a stale queue.
            PendingPresetSwitch := ""
            PresetSwitchRestartPending := false
            StopRequested := true
            if Running {
                Running := false    ; same effect as the Escape emergency stop; MainLoop exits next check
                LogMsg("Remote: STOP - macro stopped.")
                return {ok: true, msg: "Stopped."}
            }
            ; Running is false. If a session is still active (StartMacro mid startup/restart prep), the
            ; StopRequested latch above WILL abort it at StartMacro's guarded check - so this is a real
            ; stop, not a no-op, and must be acknowledged as such. Only a genuinely idle macro is rejected.
            if MacroActive {
                LogMsg("Remote: STOP - stopping the macro.")
                return {ok: true, msg: "Stopping."}
            }
            return {ok: false, msg: "Not running."}

        case "SET_ACTIVE_PRESET":
            ; Choose which preset runs on the NEXT start (same as the "Set as Active" button). This
            ; does NOT interrupt a run in progress - switching mid-run at a cycle boundary is the
            ; separate QUEUE_PRESET command below.
            if (arg = "")
                return {ok: false, msg: "No preset name given."}
            if !PresetIndex(arg)
                return {ok: false, msg: "Unknown preset: " arg}
            ActivePresetName := arg
            try IniWrite ActivePresetName, ConfigFile, GamePresetsListSection(), "Active"
            UpdateActivePresetIndicator()
            LogMsg("Remote: active preset set to '" arg "' (runs on next start).")
            return {ok: true, msg: "Active preset set to " arg "."}

        case "QUEUE_PRESET":
            ; Switch presets mid-run at the NEXT cycle boundary: MainLoop commits the queued name and
            ; StartMacro restarts into it (see PendingPresetSwitch / PresetSwitchRestartPending). Only
            ; meaningful while running - when stopped there is no boundary, so point the caller at
            ; SET_ACTIVE_PRESET instead. The name is validated to exist before it is queued (and again
            ; at the boundary, in case the preset was deleted in between).
            if (arg = "")
                return {ok: false, msg: "No preset name given."}
            if !PresetIndex(arg)
                return {ok: false, msg: "Unknown preset: " arg}
            if !Running
                return {ok: false, msg: "Not running - use SET_ACTIVE_PRESET to choose the next start."}
            PendingPresetSwitch := arg
            LogMsg("Remote: queued preset '" arg "' - switching at the next cycle boundary.")
            return {ok: true, msg: "Queued " arg " for the next cycle boundary."}

        default:
            return {ok: false, msg: "Unknown command: " verb}
    }
}

; ------------------------------------------------------------
; Status snapshot + small JSON writer
; ------------------------------------------------------------
; Writes a flat JSON snapshot of the current run state. JSON is only ever EMITTED here (never parsed
; in AHK), so a tiny hand-rolled writer is enough - no JSON-parser dependency is pulled into the app.
RemoteBridgeWriteStatus() {
    global DataDir
    global Running, Paused, DryRun
    global RunningPresetName, ActivePresetName, PendingPresetSwitch
    global LastDetectedMap, RunningScreenName, RunningStepDescription
    global ScreenRepeatCount, StepRepeatCount, StartRepeatCount, VictoryCount, DefeatCount
    global SessionId

    state := !Running ? "stopped" : (Paused ? "paused" : "running")
    ts := FormatTime(, "yyyy-MM-dd HH:mm:ss")

    json := "{`n"
    json .= '  "schema": 1,' "`n"
    json .= '  "timestamp": ' RemoteBridgeJsonStr(ts) ',' "`n"
    json .= '  "state": ' RemoteBridgeJsonStr(state) ',' "`n"
    json .= '  "running": ' (Running ? "true" : "false") ',' "`n"
    json .= '  "paused": ' (Paused ? "true" : "false") ',' "`n"
    json .= '  "dryRun": ' (DryRun ? "true" : "false") ',' "`n"
    json .= '  "activePreset": ' RemoteBridgeJsonStr(ActivePresetName) ',' "`n"
    json .= '  "runningPreset": ' RemoteBridgeJsonStr(Running ? RunningPresetName : "") ',' "`n"
    json .= '  "queuedPreset": ' RemoteBridgeJsonStr(PendingPresetSwitch) ',' "`n"
    json .= '  "currentMap": ' RemoteBridgeJsonStr(LastDetectedMap) ',' "`n"
    json .= '  "currentScreen": ' RemoteBridgeJsonStr(Running ? RunningScreenName : "") ',' "`n"
    json .= '  "currentStep": ' RemoteBridgeJsonStr(Running ? RunningStepDescription : "") ',' "`n"
    json .= '  "cycleCount": ' ScreenRepeatCount ',' "`n"
    json .= '  "stepRepeatCount": ' StepRepeatCount ',' "`n"
    json .= '  "startRepeatCount": ' StartRepeatCount ',' "`n"
    json .= '  "victoryCount": ' VictoryCount ',' "`n"
    json .= '  "defeatCount": ' DefeatCount ',' "`n"
    json .= '  "sessionId": ' RemoteBridgeJsonStr(SessionId) ',' "`n"
    json .= '  "sessionTimeMs": ' SessionElapsedMs() ',' "`n"
    json .= '  "screenTimeMs": ' RemoteBridgeJsonNumberMap(LiveScreenTimeMsSnapshot()) ',' "`n"
    json .= '  "stepTimeMs": ' RemoteBridgeJsonNumberMap(StepTimeMsSnapshot()) "`n"
    json .= "}`n"

    RemoteBridgeAtomicWrite(DataDir "\remote_status.json", json)
}

RemoteBridgeWriteAck(token, result) {
    global DataDir
    line := (token != "" ? token : "-") "|" (result.ok ? "ok" : "error") "|" result.msg "`n"
    RemoteBridgeAtomicWrite(DataDir "\remote_ack.txt", line)
}

; Wraps a value as a JSON string literal, escaping the characters JSON forbids inside a string.
RemoteBridgeJsonStr(value) {
    s := String(value)
    s := StrReplace(s, "\", "\\")
    s := StrReplace(s, '"', '\"')
    s := StrReplace(s, "`r", "")
    s := StrReplace(s, "`n", "\n")
    s := StrReplace(s, "`t", "\t")
    ; Escape any remaining C0 control character (0x00-0x1F) not already handled above - required for
    ; valid JSON. Without this, a raw backspace/form-feed/etc. in OCR text or a window title (this
    ; string is used for both, plus every log/name/path field either bridge ever sends) would produce
    ; a JSON literal that Python's json.loads rejects outright.
    out := ""
    Loop Parse s {
        code := Ord(A_LoopField)
        if (code >= 0 && code <= 0x1F)
            out .= Format("\u{:04x}", code)
        else
            out .= A_LoopField
    }
    return '"' out '"'
}

; Serializes a Map(string -> number) as a flat JSON object literal, e.g. ScreenTimeMs/StepTimeMs -
; shared by both bridges' status writers (see LocalBridgeWriteStatus/RemoteBridgeWriteStatus).
RemoteBridgeJsonNumberMap(m) {
    parts := []
    for k, v in m
        parts.Push(RemoteBridgeJsonStr(k) ":" v)
    out := "{"
    for i, p in parts {
        out .= (i > 1 ? "," : "") p
    }
    out .= "}"
    return out
}

; Publishes `content` to `path` atomically: write a temp file, then move it over the target, so a
; reader never observes a half-written file. UTF-8 without a BOM (UTF-8-RAW) - a leading BOM would
; break strict JSON parsers (e.g. Go's encoding/json). Best-effort; failures are swallowed so a
; transient I/O error can never disrupt the macro.
RemoteBridgeAtomicWrite(path, content) {
    tmp := path ".tmp"
    try {
        FileDelete tmp
    }
    try {
        FileAppend content, tmp, "UTF-8-RAW"
        FileMove tmp, path, 1
    }
}

; Start the background bridge timer. Cheap while disabled (an early return after one IniRead). Placed
; at the module's top level so it registers during the auto-execute section, exactly like the
; disconnect-detection timer.
SetTimer(RemoteBridgeTick, 500)
