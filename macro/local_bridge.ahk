; ============================================================
; LOCAL BRIDGE - always-on same-machine IPC for the PySide6 GUI
; ============================================================
; This module intentionally reuses RemoteBridgeJsonStr() and RemoteBridgeAtomicWrite() from
; remote_bridge.ahk. #Include merges both files into one global namespace, so duplicating either
; helper here would create a conflicting function definition.

LocalBridgeLastStatusTick := 0
LocalBridgeLastCmdToken := ""
; Bounds PAIR_REMOTE_AGENT's Run()+ProcessWaitClose() wait (see LocalBridgePairRemoteAgent) - a
; generous ceiling for a real network round-trip, but still a hard stop so a hung/misbehaving
; agent process can never freeze the always-on bridge (all command/status processing) forever.
LocalBridgePairProcessTimeoutSeconds := 45
; The actual outcome of the last handled command, replayed verbatim if its token is republished (a
; writer may retry before observing the ack) - replaying a hardcoded {ok:true} here would turn an
; originally REJECTED command into an apparent success on retry.
LocalBridgeLastCmdResult := {ok: true, msg: ""}
LocalConfigVersionCounter := 0
; AHK has no native null value which can be stored in a Map/Array, so JSON null decodes to this
; module-local sentinel. Command handlers reject it wherever a scalar or structured value is needed.
LocalBridgeJsonNull := {}
; This is a same-machine, single-legitimate-writer (the local Python GUI) trust boundary, not a
; remote/untrusted one - but the bridge is always-on and has no other guard against a malformed
; or buggy command payload being enormous or pathologically nested, either of which would tie up
; the one thread also responsible for every other command/status tick. Both bounds are far above
; anything a real preset/config payload would ever need.
JsonMaxTextLength := 8388608   ; 8 MiB
JsonMaxNestingDepth := 64

; Runs independently of the opt-in remote bridge. Commands are consumed first for responsiveness;
; the snapshot is then written at about eight frames per second for the local GUI.
LocalBridgeTick() {
    global LocalBridgeLastStatusTick
    LocalBridgeProcessCommand()
    if (A_TickCount - LocalBridgeLastStatusTick >= 125) {
        LocalBridgeWriteStatus()
        LocalBridgeLastStatusTick := A_TickCount
    }
}

; Reads one atomic-published local command and deletes it before dispatch, so a command cannot run
; twice if its handler later raises. Payload parsing deliberately finds only the first two pipes:
; JSON string values may legitimately contain further literal | characters.
LocalBridgeProcessCommand() {
    global DataDir, LocalBridgeLastCmdToken, LocalBridgeLastCmdResult, LocalBridgeLastStatusTick
    cmdFile := DataDir "\local_cmd.txt"
    if !FileExist(cmdFile)
        return

    raw := ""
    try raw := FileRead(cmdFile, "UTF-8")
    catch Any
        return
    try FileDelete cmdFile

    raw := Trim(raw, " `t`r`n")
    if (raw = "")
        return

    firstPipe := InStr(raw, "|")
    token := firstPipe ? Trim(SubStr(raw, 1, firstPipe - 1)) : ""
    if !firstPipe {
        LocalBridgeWriteAck(token, {ok: false, msg: "Invalid command format."})
        return
    }
    secondPipe := InStr(raw, "|", false, firstPipe + 1)
    if !secondPipe {
        LocalBridgeWriteAck(token, {ok: false, msg: "Invalid command format."})
        return
    }
    verb := Trim(SubStr(raw, firstPipe + 1, secondPipe - firstPipe - 1))
    json := SubStr(raw, secondPipe + 1)

    ; A writer may retry a command before observing its acknowledgement. Replay the ORIGINAL result
    ; verbatim rather than a hardcoded success - the first attempt may genuinely have been rejected,
    ; and reporting {ok:true} here would silently turn that rejection into an apparent success.
    if (token != "" && token = LocalBridgeLastCmdToken) {
        LocalBridgeWriteAck(token, LocalBridgeLastCmdResult)
        return
    }
    if (token != "")
        LocalBridgeLastCmdToken := token

    try result := LocalBridgeApplyCommand(verb, json)
    catch Any as err
        result := {ok: false, msg: LocalBridgeCommandErrorMessage(err)}
    LocalBridgeLastCmdResult := result
    LocalBridgeWriteAck(token, result)

    ; Publish state immediately after a command rather than waiting for the next timer interval.
    LocalBridgeWriteStatus()
    LocalBridgeLastStatusTick := A_TickCount
}

LocalBridgeCommandErrorMessage(err) {
    message := "Invalid command payload."
    try {
        if (IsObject(err) && err.HasProp("Message") && err.Message != "")
            message := err.Message
    } catch Any {
    }
    return message
}

; All known local command verbs. Unknown verbs are rejected without trying to decode an irrelevant
; payload, matching the remote bridge's default-case behavior.
LocalBridgeApplyCommand(verb, json) {
    global ConfigFile, CurrentPresetName, CurrentMapProfileName, LocalConfigVersionCounter, DataDir, OcrBusy
    if !LocalBridgeKnownVerb(verb)
        return {ok: false, msg: "Unknown command: " verb}

    payload := LocalBridgeDecodeObject(json)
    switch verb {
        case "SAVE_GENERAL":
            fields := LocalBridgeGeneralFields(payload)
            SaveGeneralFromData(fields)
            LocalBridgeSyncGeneralControls(fields)
            LocalBridgeBumpConfigVersion()
            return {ok: true, msg: "General settings saved."}

        case "SAVE_PRESET":
            return LocalBridgeSavePreset(payload)

        case "SAVE_MAP_PROFILE":
            return LocalBridgeSaveMapProfile(payload)

        case "SAVE_ADV_MAP_STEPS":
            return LocalBridgeSaveAdvMapSteps(payload)

        case "NEW_PRESET":
            result := CreatePreset(LocalBridgeTextField(payload, "name"))
            return LocalBridgeResultWithConfigVersion(result)

        case "RENAME_PRESET":
            result := RenamePreset(LocalBridgeTextField(payload, "oldName"), LocalBridgeTextField(payload, "newName"))
            return LocalBridgeResultWithConfigVersion(result)

        case "DELETE_PRESET":
            result := DeletePreset(LocalBridgeTextField(payload, "name"))
            return LocalBridgeResultWithConfigVersion(result)

        case "NEW_MAP_PROFILE":
            result := CreateMapProfile(LocalBridgeTextField(payload, "name"))
            return LocalBridgeResultWithConfigVersion(result)

        case "RENAME_MAP_PROFILE":
            result := RenameMapProfile(LocalBridgeTextField(payload, "oldName"), LocalBridgeTextField(payload, "newName"))
            return LocalBridgeResultWithConfigVersion(result)

        case "DELETE_MAP_PROFILE":
            result := DeleteMapProfile(LocalBridgeTextField(payload, "name"))
            return LocalBridgeResultWithConfigVersion(result)

        case "NEW_SCREEN":
            result := CreateScreen(LocalBridgeTextField(payload, "presetName"), LocalBridgeTextField(payload, "screenName"))
            return LocalBridgeResultWithConfigVersion(result)

        case "RENAME_SCREEN":
            result := RenameScreen(LocalBridgeTextField(payload, "presetName"), LocalBridgeTextField(payload, "oldName"), LocalBridgeTextField(payload, "newName"))
            return LocalBridgeResultWithConfigVersion(result)

        case "DELETE_SCREEN":
            result := DeleteScreen(LocalBridgeTextField(payload, "presetName"), LocalBridgeTextField(payload, "screenName"))
            return LocalBridgeResultWithConfigVersion(result)

        case "MOVE_SCREEN":
            result := MoveScreen(LocalBridgeTextField(payload, "presetName"), LocalBridgeTextField(payload, "screenName"), LocalBridgeTextField(payload, "direction"))
            return LocalBridgeResultWithConfigVersion(result)

        case "SET_ACTIVE_PRESET":
            result := RemoteBridgeApplyCommand("SET_ACTIVE_PRESET", LocalBridgeTextField(payload, "name"))
            return LocalBridgeResultWithConfigVersion(result)

        ; Reuse the cloud remote bridge (and F9/Escape hotkeys) mechanism so the Python GUI has no separate path to keep in sync.
        case "PAUSE":
            return RemoteBridgeApplyCommand("PAUSE", "")
        case "RESUME":
            return RemoteBridgeApplyCommand("RESUME", "")
        case "STOP":
            return RemoteBridgeApplyCommand("STOP", "")

        case "SET_OPTION_USED_COUNT":
            return LocalBridgeSetOptionUsedCount(payload)

        case "SET_OPTION_MAX":
            return LocalBridgeSetOptionMax(payload)

        case "EXPORT_PRESET":
            return LocalBridgeExportPreset(payload)

        case "IMPORT_PRESET":
            return LocalBridgeImportPreset(payload)

        case "START":
            startScreen := LocalBridgeTextField(payload, "startScreen", "")
            startStep := SafeInt(LocalBridgeScalarField(payload, "startStep", 0), 0)
            useActive := LocalBridgeBoolField(payload, "useActive", true)
            return LocalBridgeStartMacro(startScreen, startStep, useActive)

        case "PAIR_REMOTE_AGENT":
            return LocalBridgePairRemoteAgent(payload)

        case "START_REMOTE_AGENT":
            return LocalBridgeStartRemoteAgent(LocalBridgeTextField(payload, "agentPath"))

        case "STOP_REMOTE_AGENT":
            return LocalBridgeStopRemoteAgent(LocalBridgeTextField(payload, "agentPath", ""))

        case "START_CAPTURE":
            if LocalBridgeCaptureBusy()
                return {ok: false, msg: "A capture is already in progress."}
            BeginFieldCapture(LocalBridgeTextField(payload, "fieldId"))
            return {ok: true, msg: "Waiting for capture."}

        case "START_CAPTURE_REGION":
            if LocalBridgeCaptureBusy()
                return {ok: false, msg: "A capture is already in progress."}
            fieldIds := LocalBridgeRequireArray(LocalBridgeRequiredField(payload, "fieldIds"), "fieldIds")
            if (fieldIds.Length != 4)
                throw Error("Field 'fieldIds' must contain exactly four strings.")
            BeginRegionCapture(
                LocalBridgeScalarText(fieldIds[1], "fieldIds[1]"),
                LocalBridgeScalarText(fieldIds[2], "fieldIds[2]"),
                LocalBridgeScalarText(fieldIds[3], "fieldIds[3]"),
                LocalBridgeScalarText(fieldIds[4], "fieldIds[4]")
            )
            return {ok: true, msg: "Waiting for capture."}

        case "CANCEL_CAPTURE":
            return LocalBridgeCancelCapture()

        case "LIST_GAME_PROCESSES":
            candidates := EnumerateGameProcessCandidates()
            RemoteBridgeAtomicWrite(DataDir "\local_game_processes.json", LocalBridgeGameProcessesJson(candidates))
            return {ok: true, msg: "Found " candidates.Length " candidate window(s)."}

        case "FORCE_GAME_WINDOW":
            ok := PinClick()
            return {ok: ok, msg: ok ? "Game window pinned." : "Could not find/position the game window."}

        case "SHOW_REGION_PREVIEW":
            x1 := LocalBridgeScalarField(payload, "x1", 0)
            y1 := LocalBridgeScalarField(payload, "y1", 0)
            x2 := LocalBridgeScalarField(payload, "x2", 0)
            y2 := LocalBridgeScalarField(payload, "y2", 0)
            ; Check degeneracy here, not inside ShowRegionPreview() itself: that function is still used
            ; by the (for now) still-live native GUI's own "Show Region" buttons and must keep its
            ; MsgBox guard for them - a headless IPC caller must never be able to trigger a MsgBox.
            a := AbsXY(x1, y1)
            b := AbsXY(x2, y2)
            rect := {x: Min(a.x, b.x), y: Min(a.y, b.y), w: Abs(b.x - a.x), h: Abs(b.y - a.y)}
            if (rect.w <= 0 || rect.h <= 0)
                return {ok: false, msg: "Set both region corners first."}
            ShowRegionPreview(rect)
            return {ok: true, msg: "Preview shown."}

        case "TEST_OCR":
            ; OcrBusy also guards CheckDisconnectTick's own OCR call against the exact same hazard -
            ; RunOcrOnRegion's request/response files are shared and token-matched, so two concurrent
            ; official requests can misdirect each other's answer. Reject rather than race.
            if OcrBusy
                return {ok: false, msg: "OCR is already busy with another detection - try again shortly."}
            x1 := LocalBridgeScalarField(payload, "x1", 0)
            y1 := LocalBridgeScalarField(payload, "y1", 0)
            x2 := LocalBridgeScalarField(payload, "x2", 0)
            y2 := LocalBridgeScalarField(payload, "y2", 0)
            a := AbsXY(x1, y1)
            b := AbsXY(x2, y2)
            rect := {x: Min(a.x, b.x), y: Min(a.y, b.y), w: Abs(b.x - a.x), h: Abs(b.y - a.y)}
            if (rect.w <= 0 || rect.h <= 0)
                return {ok: false, msg: "Set both region corners first."}
            text := RunOcrOnRegion(rect.x, rect.y, rect.w, rect.h)
            return {ok: true, msg: "OCR test complete.", text: text}
    }
}

; BeginFieldCapture()/BeginRegionCapture() have no "already active" guard of their own for the
; point case (BeginRegionCapture at least no-ops via RegionCapActive, but the caller here still
; needs to know that happened) - starting a second capture while a first one is still pending would
; silently strand the first request's field id(s), which would then never resolve and just sit
; waiting until its own client-side timeout. Check both capture mechanisms before ever starting a
; new one.
LocalBridgeCaptureBusy() {
    global FieldCaptureId, RegionCapActive
    return (FieldCaptureId != "" || RegionCapActive)
}

; Lets a client that gave up waiting (its own timeout elapsed) tell AHK to stop waiting too, instead
; of leaving BeginFieldCapture/BeginRegionCapture's marker/overlay stuck open indefinitely with
; nobody watching. Reuses the exact same cleanup the Escape hotkey already performs.
LocalBridgeCancelCapture() {
    global FieldCaptureId, RegionCapActive
    if (FieldCaptureId != "") {
        CancelFieldCapture()
        return {ok: true, msg: "Capture cancelled."}
    }
    if RegionCapActive {
        CancelRegionCapture()
        return {ok: true, msg: "Capture cancelled."}
    }
    return {ok: true, msg: "No capture was in progress."}
}

LocalBridgeKnownVerb(verb) {
    static verbs := Map(
        "SAVE_GENERAL", true, "SAVE_PRESET", true, "SAVE_MAP_PROFILE", true, "SAVE_ADV_MAP_STEPS", true,
        "NEW_PRESET", true, "RENAME_PRESET", true, "DELETE_PRESET", true,
        "NEW_MAP_PROFILE", true, "RENAME_MAP_PROFILE", true, "DELETE_MAP_PROFILE", true,
        "NEW_SCREEN", true, "RENAME_SCREEN", true, "DELETE_SCREEN", true, "MOVE_SCREEN", true,
        "SET_ACTIVE_PRESET", true, "PAUSE", true, "RESUME", true, "STOP", true,
        "SET_OPTION_USED_COUNT", true, "SET_OPTION_MAX", true,
        "EXPORT_PRESET", true, "IMPORT_PRESET", true, "START", true,
        "PAIR_REMOTE_AGENT", true, "START_REMOTE_AGENT", true, "STOP_REMOTE_AGENT", true,
        "START_CAPTURE", true, "START_CAPTURE_REGION", true, "CANCEL_CAPTURE", true,
        "LIST_GAME_PROCESSES", true, "FORCE_GAME_WINDOW", true, "SHOW_REGION_PREVIEW", true, "TEST_OCR", true
    )
    return verbs.Has(verb)
}

LocalBridgeResultWithConfigVersion(result) {
    if result.ok
        LocalBridgeBumpConfigVersion()
    return result
}

LocalBridgeBumpConfigVersion() {
    global LocalConfigVersionCounter
    LocalConfigVersionCounter += 1
}

; StartMacro() blocks synchronously for the whole run (it only returns once the macro stops), and
; LocalBridgeTick is the SAME timer callback responsible for every other command/status tick -
; SetTimer skips a callback's next scheduled firing while its previous invocation hasn't returned yet,
; so calling StartMacro() directly from here would silently freeze the ENTIRE bridge (no more command
; processing, no more local_status.json updates) for the whole run, exactly when a client most needs
; PAUSE/STOP/status to keep working. Replicate StartMacro's own cheap, synchronous "already running"
; guard here so a genuinely rejected start is still answered immediately and accurately, and hand the
; real call off to its own one-shot timer thread so THIS command's ack can return right away -
; macro_log.txt (already tailed by Python) and the next local_status.json "running" snapshot are the
; source of truth for whatever StartMacro discovers after that point (a delayed rejection like a
; missing game window, or the run simply finishing).
LocalBridgeStartMacro(startScreen, startStep, useActive) {
    global Running, MacroActive
    if (Running || MacroActive)
        return {ok: false, msg: "Already running."}
    SetTimer(LocalBridgeRunStartAsync.Bind(startScreen, startStep, useActive), -1)
    return {ok: true, msg: "Starting."}
}

LocalBridgeRunStartAsync(startScreen, startStep, useActive) {
    StartMacro(startScreen, startStep, useActive)
}

; Pairing deliberately remains synchronous: unlike the common, potentially hours-long macro run,
; this is a rare setup action and the agent has no status field through which a deferred pairing
; result could be reported cleanly.
; The password/TOTP never travel through local_cmd.txt: unlike the short-lived credentials file
; (deleted the moment the agent process reads it, or right after RunWait returns here), a command
; file only gets deleted once THIS bridge actually reads it - if the app isn't running yet, is
; frozen, or a client gives up after its own send_command() timeout, an in-payload secret would sit
; in a plaintext file for an unbounded amount of time instead of a few seconds. The Python caller
; is responsible for creating `credentialsFile` (containing "<password>\n<totp>", written the same
; UTF-8-RAW way this file already requires - see the comment below) in its own short-lived temp
; location and passing only that PATH here; this handler never sees the raw secret at all.
;
; Also note for the future Python "Remote Agent Setup" caller: RunWait below is a real network
; round-trip with no client-side timeout of its own and can plausibly take much longer than typical
; bridge commands (tens of seconds on a slow connection or a 2FA challenge) - send this verb with a
; generously long send_command() timeout (not the 5s default), or a perfectly successful pairing
; will still be reported to Python as IpcTimeoutError.
LocalBridgePairRemoteAgent(payload) {
    global ConfigFile
    agentPath := Trim(LocalBridgeTextField(payload, "agentPath"))
    serverUrl := Trim(LocalBridgeTextField(payload, "serverUrl"))
    mode := LocalBridgeTextField(payload, "mode")
    email := Trim(LocalBridgeTextField(payload, "email"))
    credentialsFile := Trim(LocalBridgeTextField(payload, "credentialsFile"))
    if (mode != "login" && mode != "register")
        throw Error("Field 'mode' must be 'login' or 'register'.")
    modeFlag := (mode = "register") ? "--register" : "--login"

    if (agentPath = "" || !FileExist(agentPath))
        return {ok: false, msg: "Set a valid path to animeexpedition-agent.exe first (Browse...)."}
    if (serverUrl = "")
        return {ok: false, msg: "Enter the server URL first."}
    if (email = "")
        return {ok: false, msg: "Enter the account email first."}
    if (credentialsFile = "" || !FileExist(credentialsFile))
        return {ok: false, msg: "No credentials file was supplied."}

    IniWrite agentPath, ConfigFile, "General", "RemoteAgentPath"
    IniWrite serverUrl, ConfigFile, "General", "RemoteServerUrl"
    IniWrite email, ConfigFile, "General", "RemoteAccountEmail"
    LocalBridgeBumpConfigVersion()

    uniqueSuffix := DllCall("GetCurrentProcessId") "-" A_TickCount
    resultFile := A_Temp "\anime-expedition-auth-result-" uniqueSuffix ".txt"
    try FileDelete resultFile

    cmd := WinArgQuote(agentPath)
        . " --server " WinArgQuote(serverUrl)
        . " " WinArgQuote(modeFlag)
        . " --email " WinArgQuote(email)
        . " --credentials-file " WinArgQuote(credentialsFile)
        . " --auth-result-file " WinArgQuote(resultFile)

    ; RunWait's own block has no timeout, and this handler runs synchronously inside the
    ; always-on bridge tick (a deliberate choice for this rare, deliberate action - see the
    ; comment on LocalBridgeStartMacro for why START, unlike this, had to be deferred instead).
    ; That still leaves one real risk: an agent path pointing at a process that hangs (or
    ; simply never exits) would freeze the ENTIRE bridge - all command/status processing -
    ; indefinitely, not just for this one pairing attempt. Run()+ProcessWaitClose() with an
    ; explicit bound, plus a forced kill if that bound is exceeded, keeps this rare action from
    ; ever becoming a permanent hang, at the cost of not getting a real process exit code back
    ; (acceptable: resultFile's own content, written by the agent itself, is already the
    ; authoritative success/failure signal - the exit code was only ever a last-resort fallback
    ; for when that file comes back empty).
    pid := 0
    try {
        pid := Run(cmd, , "Hide")
    } catch as err {
        try FileDelete credentialsFile  ; the agent never ran - clean up the caller's temp file ourselves
        return {ok: false, msg: "Could not launch the agent: " err.Message}
    }
    exitedInTime := ProcessWaitClose(pid, LocalBridgePairProcessTimeoutSeconds)
    if !exitedInTime {
        try ProcessClose(pid)
        ProcessWaitClose(pid, 5)  ; brief grace period for the forced close to actually land
    }
    exitCode := exitedInTime ? 0 : 1
    try FileDelete credentialsFile  ; defense in depth - the agent also deletes this itself on read

    message := ""
    if exitedInTime
        try message := Trim(FileRead(resultFile, "UTF-8"))
    try FileDelete resultFile
    if (message = "") {
        ; A real exit code is no longer available (see the comment above) - if the process
        ; exited on its own but left no result text, that's ambiguous, not a known failure.
        message := exitedInTime
            ? "Pairing finished but produced no result message."
            : "Pairing timed out after " LocalBridgePairProcessTimeoutSeconds " seconds - the agent process was force-stopped."
    }

    LogMsg("Remote agent: " message)
    if (exitCode = 0)
        message := message "`r`n" RemoteAgentAutoStart(agentPath)
    return {ok: exitCode = 0, msg: message}
}

LocalBridgeStartRemoteAgent(agentPath) {
    message := RemoteAgentAutoStart(agentPath)
    return {ok: (message = "Agent already running." || message = "Agent started."), msg: message}
}

; `agentPath` is optional (empty string if the caller doesn't have one handy) - falls back to the
; persisted path exactly like RemoteAgentRunningPid()'s own default does. Accepting it explicitly
; matters because START_REMOTE_AGENT can be given an agentPath that was never persisted (only
; PAIR_REMOTE_AGENT writes RemoteAgentPath to config) - without this, stopping an agent started
; from a non-default path could check the wrong executable name and wrongly report it not running.
LocalBridgeStopRemoteAgent(agentPath) {
    resolvedPath := (agentPath != "") ? agentPath : Cfg("General", "RemoteAgentPath", "")
    pid := RemoteAgentRunningPid(resolvedPath)
    if !pid
        return {ok: false, msg: "Agent is not running."}
    try ProcessClose(pid)
    Sleep 200  ; brief grace period before checking whether it actually terminated
    if RemoteAgentRunningPid(resolvedPath)
        return {ok: false, msg: "Could not stop the agent (PID " pid ")."}
    LogMsg("Remote agent: stopped.")
    return {ok: true, msg: "Agent stopped."}
}

; ------------------------------------------------------------
; Status snapshot and acknowledgement writer
; ------------------------------------------------------------
LocalBridgeWriteStatus() {
    global DataDir, LocalConfigVersionCounter
    global Running, Paused, DryRun
    global RunningPresetName, ActivePresetName, PendingPresetSwitch
    global LastDetectedMap, RunningScreenName, RunningStepDescription
    global ScreenRepeatCount, StepRepeatCount, StartRepeatCount, VictoryCount, DefeatCount
    global FieldCaptureId, RegionCapFieldIds

    ts := FormatTime(, "yyyy-MM-dd HH:mm:ss")
    captureActive := (FieldCaptureId != "" || RegionCapFieldIds.Length > 0)

    json := "{`n"
    json .= '  "schema": 1,' "`n"
    json .= '  "timestamp": ' RemoteBridgeJsonStr(ts) ',' "`n"
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
    json .= '  "configVersion": ' LocalConfigVersionCounter ',' "`n"
    json .= '  "captureActive": ' (captureActive ? "true" : "false") ',' "`n"
    json .= '  "captureFieldId": ' RemoteBridgeJsonStr(FieldCaptureId) "`n"
    json .= "}`n"
    RemoteBridgeAtomicWrite(DataDir "\local_status.json", json)
}

; The result object is always flat and known at the point it is built. Deliberately keep this a
; small string writer rather than creating a generic JSON encoder alongside the decoder below.
LocalBridgeWriteAck(token, result) {
    global DataDir
    json := '{"ok":' (result.ok ? "true" : "false") ',"message":' RemoteBridgeJsonStr(result.msg)
    if result.HasProp("section")
        json .= ',"section":' RemoteBridgeJsonStr(result.section)
    if result.HasProp("filePath")
        json .= ',"filePath":' RemoteBridgeJsonStr(result.filePath)
    if result.HasProp("name")
        json .= ',"name":' RemoteBridgeJsonStr(result.name)
    if result.HasProp("text")
        json .= ',"text":' RemoteBridgeJsonStr(result.text)
    json .= "}"
    line := (token != "" ? token : "-") "|" json "`n"
    RemoteBridgeAtomicWrite(DataDir "\local_ack.txt", line)
}

LocalBridgeGameProcessesJson(candidates) {
    json := '{"processes":['
    for index, candidate in candidates {
        if (index > 1)
            json .= ","
        json .= '{"title":' RemoteBridgeJsonStr(candidate.Title) ',"process":' RemoteBridgeJsonStr(candidate.Proc) "}"
    }
    return json "]}"
}

; ------------------------------------------------------------
; SAVE_* conversions and command helpers
; ------------------------------------------------------------
LocalBridgeSavePreset(payload) {
    global CurrentPresetName
    name := LocalBridgeTextField(payload, "name")
    if !PresetIndex(name)
        throw Error("Unknown preset: " name)

    screenValues := LocalBridgeRequireArray(LocalBridgeRequiredField(payload, "screens"), "screens")
    screens := []
    for screenValue in screenValues
        screens.Push(LocalBridgeScreenFromJson(screenValue))

    optionValues := LocalBridgeRequireArray(LocalBridgeRequiredField(payload, "options"), "options")
    if (optionValues.Length != 3)
        throw Error("Field 'options' must contain exactly three objects.")
    options := []
    for optionValue in optionValues
        options.Push(LocalBridgeOptionFromJson(optionValue))

    firstScreen := screens.Length ? screens[1] : {Name: "", Steps: []}
    data := {ScreenName: firstScreen.Name, Steps: firstScreen.Steps, Options: options,
        DefaultMap: LocalBridgeTextField(payload, "defaultMap", ""),
        BackX: LocalBridgeScalarField(payload, "backX", 0),
        BackY: LocalBridgeScalarField(payload, "backY", 0),
        FallbackScreen: LocalBridgeTextField(payload, "fallbackScreen", "")}

    ; Delete old Screen* keys as DeleteScreen() does, then rebuild every submitted screen. Merely
    ; changing ScreenCount would leave stale steps in the section when a caller removes screens.
    LocalBridgeReplacePresetScreens(name, screens)
    ; This helper owns the non-screen preset fields. Its ScreenName/Steps are the first submitted
    ; screen solely to satisfy its existing explicit-data contract; all screens are already written.
    SavePresetToIni(name, data)
    if (name = CurrentPresetName)
        LoadPreset(name)
    else if (CurrentPresetName != "")
        ; SavePresetToIni() unconditionally calls LoadUsageFields(name) to refresh the legacy GUI's
        ; "Today's Challenge Usage" fields - correct when `name` is the preset actually on screen, but
        ; when the legacy GUI is showing a DIFFERENT preset, that call just repopulated its usage
        ; fields with the SAVED preset's numbers mislabeled as the DISPLAYED preset's. Left alone, an
        ; edit to one of those fields would then overwrite the displayed preset's real usage count
        ; with a number that actually belonged to the one just saved over IPC. Restore the fields to
        ; whatever preset is actually being shown.
        LoadUsageFields(CurrentPresetName)
    LocalBridgeBumpConfigVersion()
    return {ok: true, msg: "Preset saved."}
}

LocalBridgeReplacePresetScreens(name, screens) {
    global ConfigFile
    section := "Preset_" name
    content := IniRead(ConfigFile, section, , "")
    keep := []
    for line in StrSplit(content, "`n", "`r") {
        if (line = "")
            continue
        eqPos := InStr(line, "=")
        if !eqPos
            continue
        key := SubStr(line, 1, eqPos - 1)
        if !InStr(key, "Screen")
            keep.Push({Key: key, Val: SubStr(line, eqPos + 1)})
    }
    IniDelete ConfigFile, section
    for kv in keep
        IniWrite kv.Val, ConfigFile, section, kv.Key
    IniWrite screens.Length, ConfigFile, section, "ScreenCount"
    for i, screen in screens {
        WriteScreenSteps(name, i, screen.Name, screen.Steps)
        WriteScreenDetectionToIni(name, i, screen)
    }
}

LocalBridgeScreenFromJson(value) {
    screen := LocalBridgeRequireMap(value, "screen")
    stepValues := LocalBridgeRequireArray(LocalBridgeRequiredField(screen, "steps"), "screen.steps")
    steps := []
    for stepValue in stepValues
        steps.Push(LocalBridgeStepFromJson(stepValue))
    return {Name: LocalBridgeTextField(screen, "name"), Steps: steps,
        DetectionType: LocalBridgeTextField(screen, "detectionType", ""),
        DetectionX: LocalBridgeScalarField(screen, "detectionX", 0),
        DetectionY: LocalBridgeScalarField(screen, "detectionY", 0),
        DetectionEndX: LocalBridgeScalarField(screen, "detectionEndX", 0),
        DetectionEndY: LocalBridgeScalarField(screen, "detectionEndY", 0),
        DetectionText: LocalBridgeTextField(screen, "detectionText", ""),
        DefaultScreen: LocalBridgeTextField(screen, "defaultScreen", "")}
}

LocalBridgeStepFromJson(value) {
    step := LocalBridgeRequireMap(value, "step")
    return {Type: LocalBridgeTextField(step, "type"), Label: LocalBridgeTextField(step, "label", ""),
        X: LocalBridgeScalarField(step, "x", 0), Y: LocalBridgeScalarField(step, "y", 0),
        EndX: LocalBridgeScalarField(step, "endX", 0), EndY: LocalBridgeScalarField(step, "endY", 0),
        DragMs: LocalBridgeScalarField(step, "dragMs", 0),
        OncePerCycle: LocalBridgeBoolField(step, "oncePerCycle", false),
        Seconds: LocalBridgeScalarField(step, "seconds", 0),
        OnTrueScreen: LocalBridgeTextField(step, "onTrueScreen", ""),
        OnFalseScreen: LocalBridgeTextField(step, "onFalseScreen", ""),
        FallbackEnabled: LocalBridgeBoolField(step, "fallbackEnabled", false),
        FallbackMaxAttempts: LocalBridgeScalarField(step, "fallbackMaxAttempts", 0),
        FallbackScreen: LocalBridgeTextField(step, "fallbackScreen", ""),
        Advanced: LocalBridgeBoolField(step, "advanced", false),
        OutcomesRaw: LocalBridgeTextField(step, "outcomesRaw", "")}
}

LocalBridgeOptionFromJson(value) {
    option := LocalBridgeRequireMap(value, "option")
    return {Name: LocalBridgeTextField(option, "name", ""), X: LocalBridgeScalarField(option, "x", 0),
        Y: LocalBridgeScalarField(option, "y", 0), Available: LocalBridgeBoolField(option, "available", false),
        Priority: LocalBridgeScalarField(option, "priority", 0), MaxUses: LocalBridgeScalarField(option, "maxUses", 0),
        DetX: LocalBridgeScalarField(option, "detX", 0), DetY: LocalBridgeScalarField(option, "detY", 0),
        DetEndX: LocalBridgeScalarField(option, "detEndX", 0), DetEndY: LocalBridgeScalarField(option, "detEndY", 0),
        DetText: LocalBridgeTextField(option, "detText", ""), DetInvert: LocalBridgeBoolField(option, "detInvert", false)}
}

LocalBridgeSaveMapProfile(payload) {
    global CurrentMapProfileName
    name := LocalBridgeTextField(payload, "name")
    if !LocalBridgeMapProfileExists(name)
        throw Error("Unknown map profile: " name)
    placementValues := LocalBridgeRequireArray(LocalBridgeRequiredField(payload, "placements"), "placements")
    if (placementValues.Length > 10)
        throw Error("Field 'placements' accepts at most ten objects.")
    placements := []
    for placementValue in placementValues {
        placement := LocalBridgeRequireMap(placementValue, "placement")
        placements.Push({CustomSlot: LocalBridgeTextField(placement, "customSlot", ""),
            X: LocalBridgeScalarField(placement, "x", 0), Y: LocalBridgeScalarField(placement, "y", 0)})
    }
    SaveMapProfileToIni(name, LocalBridgeTextField(payload, "expectedText", ""),
        LocalBridgeBoolField(payload, "customTowers", false),
        LocalBridgeScalarField(payload, "customNumPlacements", 0), placements,
        LocalBridgeBoolField(payload, "customCamera", false))
    if (name = CurrentMapProfileName)
        LoadMapProfile(name)
    LocalBridgeBumpConfigVersion()
    return {ok: true, msg: "Map profile saved."}
}

LocalBridgeSaveAdvMapSteps(payload) {
    global CurrentMapProfileName
    mapProfileName := LocalBridgeTextField(payload, "mapProfileName")
    if (mapProfileName = "General") {
        section := "General"
    } else {
        if !LocalBridgeMapProfileExists(mapProfileName)
            throw Error("Unknown map profile: " mapProfileName)
        section := SafeInt(Cfg("MapProfile_" mapProfileName, "CustomCamera", 0), 0)
            ? "MapProfile_" mapProfileName : "General"
    }

    values := LocalBridgeRequireArray(LocalBridgeRequiredField(payload, "steps"), "steps")
    arr := []
    for value in values {
        step := LocalBridgeRequireMap(value, "advanced step")
        arr.Push({Type: LocalBridgeTextField(step, "type"), X: LocalBridgeScalarField(step, "x", 0),
            Y: LocalBridgeScalarField(step, "y", 0), EndX: LocalBridgeScalarField(step, "endX", 0),
            EndY: LocalBridgeScalarField(step, "endY", 0), DragMs: LocalBridgeScalarField(step, "dragMs", 0)})
    }
    SaveMapAdvStepsArr(section, arr)
    ; Keep the hidden legacy ListView current only when it is displaying the same effective section.
    currentSection := SafeInt(Cfg("MapProfile_" CurrentMapProfileName, "CustomCamera", 0), 0)
        ? "MapProfile_" CurrentMapProfileName : "General"
    if (section = currentSection)
        LoadMapAdvStepsLV(section)
    LocalBridgeBumpConfigVersion()
    return {ok: true, msg: "Map advanced steps saved.", section: section}
}

LocalBridgeSetOptionUsedCount(payload) {
    global CurrentPresetName, UsageUsedEdits
    presetName := LocalBridgeTextField(payload, "presetName")
    index := LocalBridgeOptionIndex(payload)
    if !PresetIndex(presetName)
        return {ok: false, msg: "Unknown preset: " presetName}
    count := SafeInt(LocalBridgeRequiredScalarField(payload, "count"), 0)
    SetOptionUsedToday("Preset_" presetName, index, count)
    if (presetName = CurrentPresetName)
        try UsageUsedEdits[index].Value := Max(0, count)
    LocalBridgeBumpConfigVersion()
    return {ok: true, msg: "Option usage count saved."}
}

LocalBridgeSetOptionMax(payload) {
    global CurrentPresetName, ConfigFile, OptData, UsageMaxEdits
    presetName := LocalBridgeTextField(payload, "presetName")
    index := LocalBridgeOptionIndex(payload)
    if !PresetIndex(presetName)
        return {ok: false, msg: "Unknown preset: " presetName}
    maximum := Max(0, SafeInt(LocalBridgeRequiredScalarField(payload, "max"), 0))
    IniWrite maximum, ConfigFile, "Preset_" presetName, "Option" index "MaxUses"
    if (presetName = CurrentPresetName) {
        try OptData[index].MaxEdit.Value := maximum
        try UsageMaxEdits[index].Value := maximum
    }
    LocalBridgeBumpConfigVersion()
    return {ok: true, msg: "Option maximum saved."}
}

LocalBridgeOptionIndex(payload) {
    index := SafeInt(LocalBridgeRequiredScalarField(payload, "optionIndex"), 0)
    if (index < 1 || index > 3)
        throw Error("optionIndex must be 1, 2, or 3.")
    return index
}

LocalBridgeExportPreset(payload) {
    global CurrentPresetName, ConfigFile
    name := LocalBridgeTextField(payload, "name")
    if !PresetIndex(name)
        return {ok: false, msg: "Unknown preset: " name}
    filePath := LocalBridgeTextField(payload, "filePath")
    if (filePath = "")
        return {ok: false, msg: "No export file path given."}
    if !RegExMatch(filePath, "\.ini$")
        filePath .= ".ini"

    ; Match ExportPresetClick(): only the currently displayed preset can have unsaved editor data.
    if (name = CurrentPresetName) {
        SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
        LocalBridgeBumpConfigVersion()
    }
    try FileDelete filePath
    content := IniRead(ConfigFile, "Preset_" name, , "")
    IniWrite name, filePath, "PresetExport", "SourceName"
    for line in StrSplit(content, "`n", "`r") {
        eq := InStr(line, "=")
        if eq
            IniWrite SubStr(line, eq + 1), filePath, "Preset", SubStr(line, 1, eq - 1)
    }
    LogMsg("Preset '" name "' exported.")
    return {ok: true, msg: "Preset exported.", filePath: filePath}
}

LocalBridgeImportPreset(payload) {
    global ConfigFile, PresetNames, presetListBox, CurrentPresetName
    filePath := LocalBridgeTextField(payload, "filePath")
    newName := Trim(LocalBridgeTextField(payload, "newName"))
    content := ""
    try content := IniRead(filePath, "Preset", , "")
    catch Any
        content := ""
    if (content = "")
        return {ok: false, msg: "That file doesn't look like an exported preset (no [Preset] section found)."}
    if (newName = "")
        return {ok: false, msg: ""}
    for existingName in PresetNames {
        if (existingName = newName)
            return {ok: false, msg: "A preset with this name already exists - pick a different name."}
    }

    if (CurrentPresetName != "")
        SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
    section := "Preset_" newName
    for line in StrSplit(content, "`n", "`r") {
        eq := InStr(line, "=")
        if eq
            IniWrite SubStr(line, eq + 1), ConfigFile, section, SubStr(line, 1, eq - 1)
    }
    PresetNames.Push(newName)
    presetListBox.Add([newName])
    presetListBox.Choose(PresetNames.Length)
    CurrentPresetName := newName
    LoadPreset(newName)
    IniWrite JoinList(PresetNames), ConfigFile, "Presets", "List"
    try editingLabel.Text := "Editing: " CurrentPresetName
    LogMsg("Preset '" newName "' imported.")
    LocalBridgeBumpConfigVersion()
    return {ok: true, msg: "Preset imported.", name: newName}
}

LocalBridgeGeneralFields(payload) {
    slotsValue := LocalBridgeRequireArray(LocalBridgeRequiredField(payload, "slots"), "slots")
    if (slotsValue.Length != 10)
        throw Error("Field 'slots' must contain exactly ten strings.")
    slots := []
    for i, value in slotsValue
        slots.Push(LocalBridgeScalarText(value, "slots[" i "]"))
    return {RoundWaitSeconds: LocalBridgeScalarField(payload, "roundWaitSeconds", 0),
        ClickDelayMs: LocalBridgeScalarField(payload, "clickDelayMs", 0),
        PlaceTowerDelayMs: LocalBridgeScalarField(payload, "placeTowerDelayMs", 0),
        AfterPlaceClick: LocalBridgeBoolField(payload, "afterPlaceClick", false),
        AfterPlaceClickX: LocalBridgeScalarField(payload, "afterPlaceClickX", 0),
        AfterPlaceClickY: LocalBridgeScalarField(payload, "afterPlaceClickY", 0),
        MaxRounds: LocalBridgeScalarField(payload, "maxRounds", 0),
        MarkerSize: LocalBridgeScalarField(payload, "markerSize", 0),
        NumPlacements: LocalBridgeScalarField(payload, "numPlacements", 0), Slots: slots,
        GameProcess: LocalBridgeTextField(payload, "gameProcess", ""),
        HoleX: LocalBridgeScalarField(payload, "holeX", 0), HoleY: LocalBridgeScalarField(payload, "holeY", 0),
        HoleW: LocalBridgeScalarField(payload, "holeW", 0), HoleH: LocalBridgeScalarField(payload, "holeH", 0),
        DisconnectEnabled: LocalBridgeBoolField(payload, "disconnectEnabled", false),
        DisconnectX1: LocalBridgeScalarField(payload, "disconnectX1", 0),
        DisconnectY1: LocalBridgeScalarField(payload, "disconnectY1", 0),
        DisconnectX2: LocalBridgeScalarField(payload, "disconnectX2", 0),
        DisconnectY2: LocalBridgeScalarField(payload, "disconnectY2", 0),
        DisconnectText: LocalBridgeTextField(payload, "disconnectText", ""),
        DisconnectReconnectX: LocalBridgeScalarField(payload, "disconnectReconnectX", 0),
        DisconnectReconnectY: LocalBridgeScalarField(payload, "disconnectReconnectY", 0),
        DisconnectIntervalSec: LocalBridgeScalarField(payload, "disconnectIntervalSec", 0),
        RemoteBridgeEnabled: LocalBridgeBoolField(payload, "remoteBridgeEnabled", false)}
}

; SAVE_GENERAL must also refresh its backing controls. StartMacro() calls SaveConfig() before it
; starts, and leaving these controls stale would immediately write the old values back over IPC data.
LocalBridgeSyncGeneralControls(fields) {
    global roundWaitEdit, clickDelayEdit, placeTowerDelayEdit, maxRoundsEdit, markerSizeEdit
    global numPlaceDdl, GeneralSlotDdls, afterPlaceClickChk, afterPlaceXEdit, afterPlaceYEdit
    global holeXEdit, holeYEdit, holeWEdit, holeHEdit, disconnectEnabledChk
    global disconnectX1Edit, disconnectY1Edit, disconnectX2Edit, disconnectY2Edit, disconnectTextEdit
    global disconnectReconnectXEdit, disconnectReconnectYEdit, disconnectIntervalEdit, remoteBridgeChk
    global gameProcessDdl
    roundWaitEdit.Value := fields.RoundWaitSeconds
    clickDelayEdit.Value := fields.ClickDelayMs
    placeTowerDelayEdit.Value := fields.PlaceTowerDelayMs
    maxRoundsEdit.Value := fields.MaxRounds
    markerSizeEdit.Value := fields.MarkerSize
    numPlaceDdl.Text := fields.NumPlacements
    for i, slot in fields.Slots
        GeneralSlotDdls[i].Text := slot
    UpdateGeneralSlotVisibility()
    afterPlaceClickChk.Value := fields.AfterPlaceClick
    afterPlaceXEdit.Value := fields.AfterPlaceClickX
    afterPlaceYEdit.Value := fields.AfterPlaceClickY
    holeXEdit.Value := fields.HoleX
    holeYEdit.Value := fields.HoleY
    holeWEdit.Value := fields.HoleW
    holeHEdit.Value := fields.HoleH
    disconnectEnabledChk.Value := fields.DisconnectEnabled
    disconnectX1Edit.Value := fields.DisconnectX1
    disconnectY1Edit.Value := fields.DisconnectY1
    disconnectX2Edit.Value := fields.DisconnectX2
    disconnectY2Edit.Value := fields.DisconnectY2
    disconnectTextEdit.Value := fields.DisconnectText
    disconnectReconnectXEdit.Value := fields.DisconnectReconnectX
    disconnectReconnectYEdit.Value := fields.DisconnectReconnectY
    disconnectIntervalEdit.Value := fields.DisconnectIntervalSec
    remoteBridgeChk.Value := fields.RemoteBridgeEnabled
    if (fields.GameProcess = "")
        gameProcessDdl.Text := ""
    else if (GetSelectedGameProcess() != fields.GameProcess) {
        ; The process list may not currently contain a process selected in Python. Keep an entry
        ; whose right-hand side is the persisted executable name so GetSelectedGameProcess() remains
        ; lossless when StartMacro() subsequently calls SaveConfig().
        gameProcessDdl.Add([fields.GameProcess " | " fields.GameProcess])
        gameProcessDdl.Text := fields.GameProcess " | " fields.GameProcess
    }
}

LocalBridgeMapProfileExists(name) {
    global MapProfileNames
    for mapName in MapProfileNames {
        if (mapName = name)
            return true
    }
    return false
}

; ------------------------------------------------------------
; JSON decoder - recursive descent, no external dependency
; ------------------------------------------------------------
JsonDecode(text) {
    global JsonMaxTextLength
    if (StrLen(text) > JsonMaxTextLength)
        throw Error("Invalid JSON: input exceeds the maximum accepted size.")
    parser := {Text: text, Pos: 1, Length: StrLen(text)}
    JsonSkipWhitespace(&parser)
    value := JsonParseValue(&parser, 0)
    JsonSkipWhitespace(&parser)
    if (parser.Pos <= parser.Length)
        throw Error("Invalid JSON: trailing data.")
    return value
}

; `depth` is an explicit parameter, not a mutable counter stored on `parser` - each recursive
; call gets its own correctly-scoped value for free via the normal call stack, so sibling
; elements in the same array/object (which must share one depth, not accumulate each other's)
; need no manual increment/decrement bookkeeping that could drift out of sync on some exit path.
JsonParseValue(&parser, depth) {
    global JsonMaxNestingDepth
    if (depth > JsonMaxNestingDepth)
        throw Error("Invalid JSON: nesting too deep.")
    if (parser.Pos > parser.Length)
        throw Error("Invalid JSON: unexpected end of input.")
    ch := SubStr(parser.Text, parser.Pos, 1)
    if (ch = "{")
        return JsonParseObject(&parser, depth)
    if (ch = "[")
        return JsonParseArray(&parser, depth)
    if (ch = '"')
        return JsonParseString(&parser)
    if (ch = "-") || RegExMatch(ch, "^\d$")
        return JsonParseNumber(&parser)
    if JsonConsumeLiteral(&parser, "true")
        return true
    if JsonConsumeLiteral(&parser, "false")
        return false
    if JsonConsumeLiteral(&parser, "null") {
        global LocalBridgeJsonNull
        return LocalBridgeJsonNull
    }
    throw Error("Invalid JSON value.")
}

JsonParseObject(&parser, depth) {
    JsonExpect(&parser, "{")
    result := Map()
    JsonSkipWhitespace(&parser)
    if JsonConsumeCharacter(&parser, "}")
        return result
    Loop {
        JsonSkipWhitespace(&parser)
        if (SubStr(parser.Text, parser.Pos, 1) != '"')
            throw Error("Invalid JSON object key.")
        key := JsonParseString(&parser)
        JsonSkipWhitespace(&parser)
        JsonExpect(&parser, ":")
        JsonSkipWhitespace(&parser)
        result[key] := JsonParseValue(&parser, depth + 1)
        JsonSkipWhitespace(&parser)
        if JsonConsumeCharacter(&parser, "}")
            return result
        JsonExpect(&parser, ",")
    }
}

JsonParseArray(&parser, depth) {
    JsonExpect(&parser, "[")
    result := []
    JsonSkipWhitespace(&parser)
    if JsonConsumeCharacter(&parser, "]")
        return result
    Loop {
        JsonSkipWhitespace(&parser)
        result.Push(JsonParseValue(&parser, depth + 1))
        JsonSkipWhitespace(&parser)
        if JsonConsumeCharacter(&parser, "]")
            return result
        JsonExpect(&parser, ",")
    }
}

JsonParseString(&parser) {
    JsonExpect(&parser, '"')
    result := ""
    while (parser.Pos <= parser.Length) {
        ch := SubStr(parser.Text, parser.Pos, 1)
        parser.Pos += 1
        if (ch = '"')
            return result
        if (ch = "\") {
            if (parser.Pos > parser.Length)
                throw Error("Invalid JSON string escape.")
            esc := SubStr(parser.Text, parser.Pos, 1)
            parser.Pos += 1
            switch esc {
                case '"': result .= '"'
                case "\": result .= "\"
                case "/": result .= "/"
                case "b": result .= Chr(8)
                case "f": result .= Chr(12)
                case "n": result .= "`n"
                case "r": result .= "`r"
                case "t": result .= "`t"
                case "u": result .= JsonParseUnicodeEscape(&parser)
                default: throw Error("Invalid JSON string escape.")
            }
            continue
        }
        if (Ord(ch) < 0x20)
            throw Error("Invalid JSON control character in string.")
        result .= ch
    }
    throw Error("Invalid JSON: unterminated string.")
}

JsonParseUnicodeEscape(&parser) {
    high := JsonReadHex4(&parser)
    if (high >= 0xD800 && high <= 0xDBFF) {
        if (SubStr(parser.Text, parser.Pos, 2) != "\u")
            throw Error("Invalid JSON Unicode surrogate pair.")
        parser.Pos += 2
        low := JsonReadHex4(&parser)
        if (low < 0xDC00 || low > 0xDFFF)
            throw Error("Invalid JSON Unicode surrogate pair.")
        return Chr(0x10000 + ((high - 0xD800) * 0x400) + low - 0xDC00)
    }
    if (high >= 0xDC00 && high <= 0xDFFF)
        throw Error("Invalid JSON Unicode surrogate pair.")
    return Chr(high)
}

JsonReadHex4(&parser) {
    if (parser.Pos + 3 > parser.Length)
        throw Error("Invalid JSON Unicode escape.")
    hex := SubStr(parser.Text, parser.Pos, 4)
    if !RegExMatch(hex, "i)^[0-9a-f]{4}$")
        throw Error("Invalid JSON Unicode escape.")
    parser.Pos += 4
    return Integer("0x" hex)
}

JsonParseNumber(&parser) {
    tail := SubStr(parser.Text, parser.Pos)
    if !RegExMatch(tail, "^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?", &match)
        throw Error("Invalid JSON number.")
    parser.Pos += StrLen(match[0])
    return Number(match[0])
}

JsonConsumeLiteral(&parser, literal) {
    if (SubStr(parser.Text, parser.Pos, StrLen(literal)) != literal)
        return false
    parser.Pos += StrLen(literal)
    return true
}

JsonExpect(&parser, expected) {
    if !JsonConsumeCharacter(&parser, expected)
        throw Error("Invalid JSON: expected '" expected "'.")
}

JsonConsumeCharacter(&parser, expected) {
    if (SubStr(parser.Text, parser.Pos, 1) != expected)
        return false
    parser.Pos += 1
    return true
}

JsonSkipWhitespace(&parser) {
    while (parser.Pos <= parser.Length) {
        ch := SubStr(parser.Text, parser.Pos, 1)
        if (ch != " " && ch != "`t" && ch != "`r" && ch != "`n")
            return
        parser.Pos += 1
    }
}

; ------------------------------------------------------------
; Decoded-value validation helpers
; ------------------------------------------------------------
LocalBridgeDecodeObject(json) {
    value := JsonDecode(json)
    return LocalBridgeRequireMap(value, "payload")
}

LocalBridgeRequireMap(value, label) {
    if !(value is Map)
        throw Error("Field '" label "' must be an object.")
    return value
}

LocalBridgeRequireArray(value, label) {
    if !(value is Array)
        throw Error("Field '" label "' must be an array.")
    return value
}

LocalBridgeRequiredField(map, key) {
    if !map.Has(key)
        throw Error("Missing required field '" key "'.")
    return map[key]
}

LocalBridgeScalarField(map, key, default) {
    value := map.Has(key) ? map[key] : default
    if IsObject(value)
        throw Error("Field '" key "' must be a scalar.")
    return value
}

LocalBridgeRequiredScalarField(map, key) {
    value := LocalBridgeRequiredField(map, key)
    if IsObject(value)
        throw Error("Field '" key "' must be a scalar.")
    return value
}

LocalBridgeTextField(map, key, default := unset) {
    if !IsSet(default)
        return LocalBridgeScalarText(LocalBridgeRequiredField(map, key), key)
    return LocalBridgeScalarText(LocalBridgeScalarField(map, key, default), key)
}

LocalBridgeBoolField(map, key, default) {
    return LocalBridgeScalarField(map, key, default) ? true : false
}

LocalBridgeScalarText(value, label) {
    if IsObject(value)
        throw Error("Field '" label "' must be a scalar.")
    return String(value)
}

; Finish initializing the local bridge BEFORE declaring the engine ready to the Python GUI. A
; local_cmd.txt can legitimately outlive an offline/crashed engine: its writer must treat a timeout
; as an unknown outcome, not as cancellation. Draining that one pending command here preserves that
; delivery contract and prevents the next GUI from being permanently blocked by the occupied
; single-slot command file.
LocalBridgeProcessCommand()
LocalBridgeWriteStatus()
LocalBridgeLastStatusTick := A_TickCount

; Register after remote_bridge.ahk so the shared writer helpers are already part of the merged script.
SetTimer(LocalBridgeTick, 125)

; The local Python GUI may now safely parse config.ini and issue a command: startup has completed,
; the bridge has published its first status snapshot, and any command left by a prior offline
; client has been consumed before this readiness marker becomes visible.
if (Cfg("General", "CoordFormat", "") = "percent")
    RemoteBridgeAtomicWrite(DataDir "\engine_ready.txt", "")
