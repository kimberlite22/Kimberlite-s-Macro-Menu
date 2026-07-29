; ============================================================
; LOCAL BRIDGE - always-on same-machine IPC for the PySide6 GUI
; ============================================================
; This module intentionally reuses RemoteBridgeJsonStr() and RemoteBridgeAtomicWrite() from
; remote_bridge.ahk. #Include merges both files into one global namespace, so duplicating either
; helper here would create a conflicting function definition.

LocalBridgeLastStatusTick := 0
LocalBridgeLastCmdToken := ""
; The actual outcome of the last handled command, replayed verbatim if its token is republished (a
; writer may retry before observing the ack) - replaying a hardcoded {ok:true} here would turn an
; originally REJECTED command into an apparent success on retry.
LocalBridgeLastCmdResult := {ok: true, msg: ""}
LocalConfigVersionCounter := 0
; AHK has no native null value which can be stored in a Map/Array, so JSON null decodes to this
; module-local sentinel. Command handlers reject it wherever a scalar or structured value is needed.
LocalBridgeJsonNull := {}

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
    global ConfigFile, CurrentPresetName, CurrentMapProfileName, LocalConfigVersionCounter
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

        case "START_CAPTURE":
            BeginFieldCapture(LocalBridgeTextField(payload, "fieldId"))
            return {ok: true, msg: "Waiting for capture."}

        case "START_CAPTURE_REGION":
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
    }
}

LocalBridgeKnownVerb(verb) {
    static verbs := Map(
        "SAVE_GENERAL", true, "SAVE_PRESET", true, "SAVE_MAP_PROFILE", true, "SAVE_ADV_MAP_STEPS", true,
        "NEW_PRESET", true, "RENAME_PRESET", true, "DELETE_PRESET", true,
        "NEW_MAP_PROFILE", true, "RENAME_MAP_PROFILE", true, "DELETE_MAP_PROFILE", true,
        "NEW_SCREEN", true, "RENAME_SCREEN", true, "DELETE_SCREEN", true, "MOVE_SCREEN", true,
        "SET_ACTIVE_PRESET", true, "SET_OPTION_USED_COUNT", true, "SET_OPTION_MAX", true,
        "EXPORT_PRESET", true, "IMPORT_PRESET", true, "START", true,
        "START_CAPTURE", true, "START_CAPTURE_REGION", true
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
    json .= "}"
    line := (token != "" ? token : "-") "|" json "`n"
    RemoteBridgeAtomicWrite(DataDir "\local_ack.txt", line)
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
    for i, screen in screens
        WriteScreenSteps(name, i, screen.Name, screen.Steps)
}

LocalBridgeScreenFromJson(value) {
    screen := LocalBridgeRequireMap(value, "screen")
    stepValues := LocalBridgeRequireArray(LocalBridgeRequiredField(screen, "steps"), "screen.steps")
    steps := []
    for stepValue in stepValues
        steps.Push(LocalBridgeStepFromJson(stepValue))
    return {Name: LocalBridgeTextField(screen, "name"), Steps: steps}
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
    parser := {Text: text, Pos: 1, Length: StrLen(text)}
    JsonSkipWhitespace(&parser)
    value := JsonParseValue(&parser)
    JsonSkipWhitespace(&parser)
    if (parser.Pos <= parser.Length)
        throw Error("Invalid JSON: trailing data.")
    return value
}

JsonParseValue(&parser) {
    if (parser.Pos > parser.Length)
        throw Error("Invalid JSON: unexpected end of input.")
    ch := SubStr(parser.Text, parser.Pos, 1)
    if (ch = "{")
        return JsonParseObject(&parser)
    if (ch = "[")
        return JsonParseArray(&parser)
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

JsonParseObject(&parser) {
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
        result[key] := JsonParseValue(&parser)
        JsonSkipWhitespace(&parser)
        if JsonConsumeCharacter(&parser, "}")
            return result
        JsonExpect(&parser, ",")
    }
}

JsonParseArray(&parser) {
    JsonExpect(&parser, "[")
    result := []
    JsonSkipWhitespace(&parser)
    if JsonConsumeCharacter(&parser, "]")
        return result
    Loop {
        JsonSkipWhitespace(&parser)
        result.Push(JsonParseValue(&parser))
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

; Register after remote_bridge.ahk so the shared writer helpers are already part of the merged script.
SetTimer(LocalBridgeTick, 125)
