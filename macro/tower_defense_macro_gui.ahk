#Requires AutoHotkey v2.0
#SingleInstance Force
CoordMode "Pixel", "Screen"
CoordMode "Mouse", "Screen"
CoordMode "ToolTip", "Screen"

; Keep this in sync with the release tag (v0.3.0, v0.4.0, ...). The release workflow refuses to
; publish when the tag and this value differ, so every EXE can reliably compare itself with the
; latest GitHub release.
AppName := "Kimberlite's Macro Menu"
; The project's previous name, kept only so MigratePortableData/CleanupLegacyInstallation can find
; and retire a per-user install/data directory left behind by this rename. Update this to the
; current AppName (moving it one hop forward) the next time the project is renamed again, the same
; way this value itself replaced the even-older "Anime Expedition Macro" (no "Kimberlite's" prefix).
LegacyAppName := "Kimberlite's Anime Expedition Macro"
AppVersion := "0.4.16"
ReleaseBaseUrl := "https://github.com/kimberlite22/Kimberlite-s-Macro-Menu/releases/latest/download/"
ReleaseExeName := "Kimberlites-Macro-Menu.exe"
UpdateCheckBusy := false
; gui.exe is becoming the primary launched process, so its --headless engine must not install,
; create shortcuts, prompt for updates, or show UI; gui.exe owns those user-facing responsibilities.
IsHeadlessEngine := false
for arg in A_Args {
    if (arg = "--headless") {
        IsHeadlessEngine := true
        break
    }
}
if IsHeadlessEngine
    A_IconHidden := true

; AutoHotkey's own unhandled-exception dialog (Continue/Abort/ExitApp) is MODAL and blocks the
; entire script - every GUI, hotkey and timer - until someone answers it. Since this macro drives a
; fullscreen game, that dialog can pop up BEHIND the game window where the user never sees it, so an
; uncaught edge case anywhere (e.g. the Remote Agent Setup window's pairing flow) leaves the whole
; app silently frozen with no visible cause - indistinguishable from it having closed once the user
; gives up and kills the process. Registering OnError and returning true skips that built-in dialog
; entirely, so no human interaction is required to keep going: the offending thread just ends and
; the rest of the app (main GUI, macro loop) keeps running. The replacement MsgBox below is
; best-effort visibility only (capped with a timeout so it can never itself become the next hang) -
; the log line right before it is the reliable record. Registered THIS early (before
; MigratePortableData/EnsureCompiledAppInstalled/EnsureAppDirectories below) so a failure in any of
; them - including in a headless engine, which must never surface AHK's default modal dialog at all
; - is caught by the headless-aware handler below instead of the built-in one.
OnError(ReportUnhandledError)

; Nothing this engine spawns may outlive it. Registered just as early and for the same reason: the
; exits below (a failed install/migration calling ExitApp) are real exit paths too, and every exit
; path used to leak the OCR helpers. The handler itself is safe this early - it only acts on helper
; PIDs, which are still 0 until something starts one. See ReapHelperProcesses for what it stops, and
; EnsureHelperJob for the kill-on-close backstop that covers the exits this can never see.
OnExit(ReapHelperProcesses)

; A release EXE is a small per-user installer as well as the app itself. LocalAppData\Programs is
; Windows' standard writable per-user application location: no administrator prompt is needed,
; self-updates can replace the EXE, and a Start Menu shortcut makes the app searchable by name.
; Mutable config/log/protocol files live in a separate LocalAppData data directory.
InstallTestRoot := A_IsCompiled ? Trim(EnvGet("AEM_TEST_ROOT")) : ""
LocalAppDataDir := A_IsCompiled ? EnvGet("LOCALAPPDATA") : ""
if (A_IsCompiled && InstallTestRoot != "") {
    InstallDir := InstallTestRoot "\Programs\" AppName
    DataDir := InstallTestRoot "\AppData\" AppName
    StartMenuDir := InstallTestRoot "\Start Menu\Programs"
    LegacyInstallDir := InstallTestRoot "\Programs\" LegacyAppName
    LegacyDataDir := InstallTestRoot "\AppData\" LegacyAppName
} else if A_IsCompiled {
    InstallDir := LocalAppDataDir "\Programs\" AppName
    DataDir := LocalAppDataDir "\" AppName
    StartMenuDir := A_Programs
    LegacyInstallDir := LocalAppDataDir "\Programs\" LegacyAppName
    LegacyDataDir := LocalAppDataDir "\" LegacyAppName
} else {
    ; Developer/source runs remain self-contained and do not install or touch the Start Menu.
    InstallDir := A_ScriptDir
    DataDir := A_ScriptDir
    StartMenuDir := ""
    LegacyInstallDir := ""
    LegacyDataDir := ""
}
RuntimeDir := A_IsCompiled ? InstallDir : A_ScriptDir
InstalledExePath := InstallDir "\" ReleaseExeName
StartMenuShortcutPath := A_IsCompiled ? StartMenuDir "\" AppName ".lnk" : ""
LegacyStartMenuShortcutPath := A_IsCompiled ? StartMenuDir "\" LegacyAppName ".lnk" : ""
; Assigned this early (DataDir is already known above) so ReportUnhandledError - registered even
; earlier still - always has a real LogFile to write to, including for a failure in
; MigratePortableData/EnsureCompiledAppInstalled/EnsureAppDirectories/EnsureBundledRuntimeFiles
; below, all of which run before this used to be assigned.
LogFile := DataDir "\macro_log.txt"

if A_IsCompiled
    MigratePortableData(LegacyDataDir)
if !IsHeadlessEngine
    EnsureCompiledAppInstalled()
EnsureAppDirectories()
; A readiness marker from a crashed prior instance must never make a new GUI believe this engine
; is ready before this launch has loaded and migrated its configuration.
try FileDelete DataDir "\engine_ready.txt"
EnsureBundledRuntimeFiles()
if !IsHeadlessEngine
    EnsureStartMenuShortcut()
if (A_IsCompiled && !IsHeadlessEngine)
    SetTimer CleanupLegacyInstallation, -2000

; Many games (Roblox included) only reliably react to input sent via "Event" mode - it uses
; the older mouse_event/keybd_event Windows APIs, which some games' raw/DirectInput handling
; accepts where the default SendInput mode is silently ignored (menu clicks can work while
; world/game clicks don't, since those often go through a different input path).
; NOTE: "Play" mode was tried first but failed to move the cursor at all on this system -
; Event mode still uses real cursor movement, so it's the safer choice here.
SendMode "Event"
SetMouseDelay 10
SetKeyDelay 20, 20

ConfigFile := DataDir "\config.ini"

; OnError(ReportUnhandledError) is registered much earlier now (right after IsHeadlessEngine is
; computed, near the top of the file) - see the comment there for why - so it is already active
; before ConfigFile/LogFile above and everything below are even assigned.

ReportUnhandledError(err, mode) {
    global LogFile, AppName, IsHeadlessEngine
    ; `throw` can raise any value, not just an Error object, so reading `err.Message`/`.File`/`.Line`
    ; below could itself fail - and a PLAIN `catch` only matches Error (it means `catch Error`), so it
    ; would miss a non-Error failure the same way the bare `try` this replaced did. `catch Any` is the
    ; form that matches every thrown value regardless of type - confirmed empirically (a plain `catch`
    ; provably let a raw thrown string straight through in this AutoHotkey version; `catch Any` caught
    ; the same throw). That is what actually closes this off, not just an explicit catch clause.
    text := "Unhandled error"
    try {
        message := (IsObject(err) && err.HasProp("Message")) ? err.Message : String(err)
        text := "Unhandled error: " message
        if (IsObject(err) && err.HasProp("File") && err.File != "" && err.HasProp("Line"))
            text .= " (" err.File ":" err.Line ")"
    } catch Any {
        ; text keeps its fallback value set above
    }
    try FileAppend FormatTime(, "yyyy-MM-dd HH:mm:ss") " - " text "`n", LogFile
    ; A headless engine has nobody at the keyboard to see or dismiss this - the log line above is
    ; already the only record anyone (gui.exe, tailing macro_log.txt) will ever see of it.
    if !IsHeadlessEngine
        try MsgBox(
            text "`n`n" (mode = "ExitApp"
                ? "This happened during startup - " AppName " may not continue."
                : AppName " will keep running, but the action that triggered this did not complete."),
            AppName " - Unexpected Error",
            "Iconx T20"
        )
    return true
}

; Check before constructing/showing the macro GUI. If a newer version exists, the user is asked
; whether to install it; on Yes, the helper replaces the installed EXE and relaunches it. Either
; way (No, or no update available), startup continues normally into the macro.
if !IsHeadlessEngine
    CheckForUpdates()

Cfg(section, key, default) {
    global ConfigFile
    return IniRead(ConfigFile, section, key, default)
}

; Bring older configs (absolute-pixel coordinates) up to the current percent-of-opening format,
; ONCE, before any value is read into the GUI. See MigrateCoordsToPercent for the how/why.
MigrateCoordsToPercent()

; Wrap a pre-multi-game config's single implicit game into [Game_<default>], ONCE. Must run AFTER
; MigrateCoordsToPercent (so it only ever has to move already-percent-format data) and BEFORE
; InitGames/InitMapProfiles/InitPresets (so those always find a valid, already-game-scoped config).
; See MigrateToGames for the how/why.
MigrateToGames()

; Put a game window's title bar back when the option that took it away is no longer on. This is the
; recovery half of the fullscreen opening: the marker on disk outlives a crash or a taskkill, so a
; run that never reached its own cleanup still cannot leave the user with a window they can neither
; move nor close. Nothing happens when there is no marker, and a marker is deliberately LEFT alone
; while the option is still on, since the window is meant to be borderless then.
if !FullscreenOpeningEnabled()
    RestoreGameWindowFrame()

; Robust integer parser for user-entered numeric fields (coordinates, delays, wait times, ...).
; Accepts a comma as a decimal separator (e.g. German keyboards/locale produce "0,1" instead of
; "0.1") as well as a period, trims whitespace, and falls back to `def` for anything that still
; isn't a valid number - instead of crashing the whole macro with an Integer.Call type error.
SafeInt(val, def := 0) {
    s := Trim(String(val))
    if (s = "")
        return def
    s := StrReplace(s, ",", ".")
    if !IsNumber(s)
        return def
    return Integer(Round(Number(s)))
}

; Same as SafeInt but keeps fractional values (used for wait-after times, which support decimal
; seconds, e.g. "0.5" or - once the comma is normalized to a period - "0,5").
SafeNum(val, def := 0.0) {
    s := Trim(String(val))
    if (s = "")
        return def
    s := StrReplace(s, ",", ".")
    if !IsNumber(s)
        return def
    return Number(s)
}

; ============================================================
; WINDOWS APP INSTALLATION + SELF-UPDATER
; ============================================================
NormalizeWindowsPath(path) {
    return StrLower(RTrim(StrReplace(path, "/", "\"), "\"))
}

PathsEqual(left, right) {
    return NormalizeWindowsPath(left) = NormalizeWindowsPath(right)
}

EnsureAppDirectories() {
    global InstallDir, DataDir, AppName, IsHeadlessEngine
    if !A_IsCompiled
        return
    try {
        if !DirExist(InstallDir)
            DirCreate InstallDir
        if !DirExist(DataDir)
            DirCreate DataDir
    } catch as err {
        ; Neither InstallDir nor DataDir is guaranteed to exist at this point (that is exactly what
        ; just failed), so a headless engine's only realistic diagnostic trail is A_Temp - nobody is
        ; watching for a MsgBox on a hidden background process, and it would otherwise block ExitApp
        ; indefinitely (this MsgBox has no "T" timeout, unlike ReportUnhandledError's).
        if IsHeadlessEngine {
            try FileAppend(
                FormatTime(, "yyyy-MM-dd HH:mm:ss") " - FATAL: application folders could not be prepared (" err.Message ").`n",
                A_Temp "\" AppName " startup error.txt"
            )
        } else {
            MsgBox(
                "The application folders could not be prepared.`n`n" err.Message,
                AppName,
                "Iconx"
            )
        }
        ExitApp
    }
}

MigratePortableData(sourceDir) {
    global DataDir
    if (PathsEqual(sourceDir, DataDir))
        return

    if !DirExist(DataDir)
        DirCreate DataDir

    ; Never overwrite data that already belongs to an installed copy.
    for fileName in ["config.ini", "macro_log.txt"] {
        sourcePath := sourceDir "\" fileName
        destinationPath := DataDir "\" fileName
        if (FileExist(sourcePath) && !FileExist(destinationPath))
            FileCopy sourcePath, destinationPath
    }

    sourceBackups := sourceDir "\config_backups"
    destinationBackups := DataDir "\config_backups"
    if DirExist(sourceBackups) {
        if !DirExist(destinationBackups)
            DirCreate destinationBackups
        Loop Files sourceBackups "\*.ini", "F" {
            destinationPath := destinationBackups "\" A_LoopFileName
            if !FileExist(destinationPath)
                FileCopy A_LoopFileFullPath, destinationPath
        }
    }
}

EnsureCompiledAppInstalled() {
    global InstallDir, InstalledExePath, AppName
    if (!A_IsCompiled || PathsEqual(A_ScriptFullPath, InstalledExePath))
        return

    stagedExe := InstalledExePath ".installing"
    try {
        if !DirExist(InstallDir)
            DirCreate InstallDir
        MigratePortableData(A_ScriptDir)

        try FileDelete stagedExe
        FileCopy A_ScriptFullPath, stagedExe, 1
        FileMove stagedExe, InstalledExePath, 1
        EnsureStartMenuShortcut()

        Run '"' InstalledExePath '"'
        ExitApp
    } catch as err {
        try FileDelete stagedExe
        MsgBox(
            AppName " could not be installed for the current Windows user.`n`n"
            "Close any running copy and try again.`n`n" err.Message,
            AppName " Setup",
            "Iconx"
        )
        ExitApp
    }
}

EnsureStartMenuShortcut() {
    global InstallDir, InstalledExePath, StartMenuDir, StartMenuShortcutPath, AppName
    if !A_IsCompiled
        return
    try {
        if !DirExist(StartMenuDir)
            DirCreate StartMenuDir
        FileCreateShortcut(
            InstalledExePath,
            StartMenuShortcutPath,
            InstallDir,
            ,
            "Launch " AppName,
            InstalledExePath
        )
    } catch as err {
        MsgBox(
            "The Windows Start Menu shortcut could not be created.`n`n" err.Message,
            AppName " Setup",
            "Icon!"
        )
    }
}

CleanupLegacyInstallation(*) {
    global LegacyInstallDir, InstallDir, LegacyStartMenuShortcutPath, StartMenuShortcutPath
    if !A_IsCompiled
        return

    if (
        LegacyStartMenuShortcutPath != ""
        && !PathsEqual(LegacyStartMenuShortcutPath, StartMenuShortcutPath)
        && FileExist(LegacyStartMenuShortcutPath)
    )
        try FileDelete LegacyStartMenuShortcutPath

    ; The legacy data directory deliberately remains as a safety copy. Only obsolete program files
    ; and the old Start Menu shortcut are removed after the renamed app is already running.
    if (
        LegacyInstallDir != ""
        && !PathsEqual(LegacyInstallDir, InstallDir)
        && DirExist(LegacyInstallDir)
    )
        try DirDelete LegacyInstallDir, 1
}

EnsureBundledRuntimeFiles() {
    global RuntimeDir, AppName, DataDir, IsHeadlessEngine
    if !A_IsCompiled
        return

    ocrServerPath := RuntimeDir "\ocr_server.exe"
    try {
        FileInstall "ocr_server.exe", ocrServerPath, 1
    } catch as err {
        ; The only recoverable overwrite failure is a live OCR helper holding the expected regular
        ; helper file open. An arbitrary existing file is not enough evidence; otherwise a
        ; corrupt/missing bundle, bad destination, or access failure would be hidden.
        existingOcrHelper := FileExist(ocrServerPath) && !DirExist(ocrServerPath)
        activeOcrHelper := ProcessExist("ocr_server.exe")
        if (activeOcrHelper && existingOcrHelper) {
            try FileAppend(
                FormatTime(, "yyyy-MM-dd HH:mm:ss") " - OCR helper: could not refresh ocr_server.exe (" err.Message "). Using the existing copy.`n",
                DataDir "\macro_log.txt"
            )
        } else {
            ; EnsureAppDirectories() has already run by this point (see the startup sequence), so DataDir
            ; exists - but a headless engine has nobody watching for a MsgBox (no "T" timeout here either,
            ; so it would otherwise block ExitApp indefinitely on a hidden background process).
            if IsHeadlessEngine {
                try FileAppend(
                    FormatTime(, "yyyy-MM-dd HH:mm:ss") " - FATAL: OCR helper files could not be prepared (" err.Message ").`n",
                    DataDir "\macro_log.txt"
                )
            } else {
                MsgBox(
                    "The OCR helper files could not be prepared in the application folder.`n`n"
                    err.Message,
                    AppName,
                    "Iconx"
                )
            }
            ExitApp
        }
    }

    ; The remote agent is optional (off by default - "Enable remote bridge" checkbox), so unlike
    ; the OCR helper above, a failure here must not take down the whole app: it just leaves the
    ; Remote Agent Setup window's path empty (or, on an update, a stale previous copy in place -
    ; e.g. because the agent .exe was running and locked the file) until the user Browses by hand
    ; or restarts once the lock clears. Logged (best-effort, via a direct FileAppend rather than
    ; LogMsg) so a stale bundled copy after an update is at least visible in macro_log.txt - LogMsg
    ; itself is unusable this early because it reads DryRun/LogLines, neither of which is assigned
    ; until after this function returns. The release workflow builds
    ; remote/agent/animeexpedition-agent.exe with `go build` before Ahk2Exe compiles this script,
    ; so it exists to embed at compile time.
    try
        FileInstall "..\remote\agent\animeexpedition-agent.exe", RuntimeDir "\animeexpedition-agent.exe", 1
    catch as err {
        try FileAppend(
            FormatTime(, "yyyy-MM-dd HH:mm:ss") " - Remote agent: could not refresh the bundled animeexpedition-agent.exe (" err.Message "). A previous copy, if any, is still in place.`n",
            DataDir "\macro_log.txt"
        )
    }
}

HttpGetText(url) {
    global AppVersion
    req := ComObject("WinHttp.WinHttpRequest.5.1")
    req.SetTimeouts(3000, 3000, 5000, 15000)
    req.Open("GET", url, false)
    req.SetRequestHeader("User-Agent", "Kimberlites-Macro-Menu/" AppVersion)
    req.Send()
    if (req.Status != 200)
        throw Error("HTTP " req.Status " while downloading " url)
    return req.ResponseText
}

ShowUpdateProgressGui() {
    global AppName
    ; The automatic update is deliberately non-cancellable.
    progressGui := Gui("-SysMenu", AppName " Update")
    status := progressGui.AddText("w280", "Downloading update...")
    bar := progressGui.AddProgress("w280 Range0-100", 0)
    progressGui.Show()
    return { gui: progressGui, status: status, bar: bar }
}

DownloadBinaryWithProgress(url, destination, statusCtrl, progressBar) {
    global AppVersion
    if !RegExMatch(url, "i)^https://([^/]+)(/.*)$", &match)
        throw Error("The update download URL is invalid.")

    session := 0
    connection := 0
    request := 0
    file := ""
    try {
        session := DllCall(
            "winhttp\WinHttpOpen",
            "Str", "Kimberlites-Macro-Menu/" AppVersion,
            "UInt", 0,
            "Ptr", 0,
            "Ptr", 0,
            "UInt", 0,
            "Ptr"
        )
        if !session
            throw Error("Could not open a WinHTTP session for the update download.")
        ; Without explicit timeouts, WinHTTP's resolve timeout defaults to infinite, which could
        ; hang startup forever on a stalled DNS lookup. Match the bounded timeouts the old
        ; WinHttpRequest-based downloader used (resolve, connect, send, receive - milliseconds).
        DllCall("winhttp\WinHttpSetTimeouts", "Ptr", session, "Int", 5000, "Int", 5000, "Int", 10000, "Int", 60000)

        connection := DllCall(
            "winhttp\WinHttpConnect",
            "Ptr", session,
            "Str", match[1],
            "UShort", 443,
            "UInt", 0,
            "Ptr"
        )
        if !connection
            throw Error("Could not connect to the update server.")

        ; Read the response in chunks because WinHttpRequest COM exposes no incremental progress.
        request := DllCall(
            "winhttp\WinHttpOpenRequest",
            "Ptr", connection,
            "Str", "GET",
            "Str", match[2],
            "Ptr", 0,
            "Ptr", 0,
            "Ptr", 0,
            "UInt", 0x00800000,
            "Ptr"
        )
        if !request
            throw Error("Could not open the update download request.")
        if !DllCall(
            "winhttp\WinHttpSendRequest",
            "Ptr", request,
            "Ptr", 0,
            "UInt", 0,
            "Ptr", 0,
            "UInt", 0,
            "UInt", 0,
            "Ptr", 0,
            "Int"
        )
            throw Error("Could not send the update download request.")
        if !DllCall("winhttp\WinHttpReceiveResponse", "Ptr", request, "Ptr", 0, "Int")
            throw Error("Could not receive the update download response.")

        statusCode := 0
        statusSize := 4
        headerIndex := 0
        if !DllCall(
            "winhttp\WinHttpQueryHeaders",
            "Ptr", request,
            "UInt", 19 | 0x20000000,
            "Ptr", 0,
            "UInt*", &statusCode,
            "UInt*", &statusSize,
            "UInt*", &headerIndex,
            "Int"
        )
            throw Error("Could not read the update download status.")
        if (statusCode != 200)
            throw Error("HTTP " statusCode " while downloading the update.")

        totalBytes := 0
        totalSize := 4
        headerIndex := 0
        DllCall(
            "winhttp\WinHttpQueryHeaders",
            "Ptr", request,
            "UInt", 5 | 0x20000000,
            "Ptr", 0,
            "UInt*", &totalBytes,
            "UInt*", &totalSize,
            "UInt*", &headerIndex,
            "Int"
        )

        try FileDelete destination
        file := FileOpen(destination, "w")
        if !file
            throw Error("Could not create the update download file.")

        receivedBytes := 0
        loop {
            available := 0
            if !DllCall("winhttp\WinHttpQueryDataAvailable", "Ptr", request, "UInt*", &available, "Int")
                throw Error("Could not read update download data.")
            if (available = 0)
                break

            chunk := Buffer(Min(available, 65536))
            bytesRead := 0
            if !DllCall(
                "winhttp\WinHttpReadData",
                "Ptr", request,
                "Ptr", chunk.Ptr,
                "UInt", chunk.Size,
                "UInt*", &bytesRead,
                "Int"
            )
                throw Error("Could not download update data.")
            if (bytesRead = 0)
                continue

            file.RawWrite(chunk, bytesRead)
            receivedBytes += bytesRead
            receivedMB := Round(receivedBytes / (1024 * 1024), 1)
            if (totalBytes > 0) {
                totalMB := Round(totalBytes / (1024 * 1024), 1)
                statusCtrl.Text := "Downloading update... " receivedMB " MB / " totalMB " MB"
                progressBar.Value := Min(100, Floor(receivedBytes * 100 / totalBytes))
            } else {
                statusCtrl.Text := "Downloading update... " receivedMB " MB"
            }
            Sleep(1) ; Let the progress window repaint before the next network read can block.
        }

        file.Close()
        file := ""
    } finally {
        if IsObject(file)
            file.Close()
        if request
            DllCall("winhttp\WinHttpCloseHandle", "Ptr", request, "Int")
        if connection
            DllCall("winhttp\WinHttpCloseHandle", "Ptr", connection, "Int")
        if session
            DllCall("winhttp\WinHttpCloseHandle", "Ptr", session, "Int")
    }
}

ParseUpdateMetadata(text) {
    values := Map()
    for line in StrSplit(StrReplace(text, "`r"), "`n") {
        line := Trim(line)
        if (line = "" || SubStr(line, 1, 1) = "#")
            continue
        separator := InStr(line, "=")
        if separator
            values[StrLower(Trim(SubStr(line, 1, separator - 1)))] := Trim(SubStr(line, separator + 1))
    }
    return values
}

PsSingleQuote(value) {
    return StrReplace(value, "'", "''")
}

; Quotes `value` as ONE argv element the way CreateProcess/CommandLineToArgvW (and therefore Go's
; os.Args) expect - see Microsoft's documented algorithm ("Everyone quotes command line arguments
; the wrong way"). Run/RunWait invoke CreateProcess directly for a plain "<exe> <params>" target
; (no cmd.exe involved, unlike the A_ComSpec calls elsewhere in this file), so this is the ONLY
; place a value can escape its own argument - it must be used for every dynamic string (paths,
; URLs, pairing codes) built into a Run/RunWait command line, so nothing the user types can inject
; an extra flag or argument into the launched process.
WinArgQuote(value) {
    if (value != "" && !InStr(value, " ") && !InStr(value, "`t") && !InStr(value, '"'))
        return value
    out := '"'
    backslashes := 0
    Loop Parse, value {
        ch := A_LoopField
        if (ch = "\") {
            backslashes += 1
        } else if (ch = '"') {
            Loop (backslashes * 2 + 1)
                out .= "\"
            out .= '"'
            backslashes := 0
        } else {
            Loop backslashes
                out .= "\"
            backslashes := 0
            out .= ch
        }
    }
    Loop (backslashes * 2)
        out .= "\"
    out .= '"'
    return out
}

GetFileSha256(path) {
    outputPath := A_Temp "\anime-expedition-hash-" DllCall("GetCurrentProcessId") "-" A_TickCount ".txt"
    ps :=
        "$h=(Get-FileHash -LiteralPath '" PsSingleQuote(path) "' -Algorithm SHA256).Hash;"
        . "[IO.File]::WriteAllText('" PsSingleQuote(outputPath) "',$h)"
    exitCode := RunWait(
        'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -Command "' ps '"',
        ,
        "Hide"
    )
    if (exitCode != 0 || !FileExist(outputPath))
        throw Error("The downloaded update could not be verified.")
    try {
        return Trim(FileRead(outputPath, "UTF-8"))
    } finally {
        try FileDelete outputPath
    }
}

StartSelfUpdate(newExePath) {
    updaterPath := A_Temp "\anime-expedition-updater-" DllCall("GetCurrentProcessId") "-" A_TickCount ".ps1"
    script := "param([int]$ParentPid,[string]$CurrentExe,[string]$NewExe)`r`n"
    script .= "$ErrorActionPreference = 'Stop'`r`n"
    script .= "try { Wait-Process -Id $ParentPid -Timeout 30 -ErrorAction SilentlyContinue } catch {}`r`n"
    script .= "$installed = $false`r`n"
    script .= "for ($attempt = 0; $attempt -lt 50; $attempt++) {`r`n"
    script .= "  try {`r`n"
    script .= "    [IO.File]::Copy($NewExe, $CurrentExe, $true)`r`n"
    script .= "    $installed = $true`r`n"
    script .= "    break`r`n"
    script .= "  } catch { Start-Sleep -Milliseconds 200 }`r`n"
    script .= "}`r`n"
    script .= "if ($installed) {`r`n"
    script .= "  Remove-Item -LiteralPath $NewExe -Force -ErrorAction SilentlyContinue`r`n"
    script .= "  Start-Process -FilePath $CurrentExe`r`n"
    script .= "} else {`r`n"
    script .= "  Add-Type -AssemblyName PresentationFramework`r`n"
    script .= "  [System.Windows.MessageBox]::Show('The update could not replace the current EXE. Move it to a writable folder and try again.','Kimberlite''s Macro Menu Update') | Out-Null`r`n"
    script .= "}`r`n"
    script .= "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue`r`n"
    FileAppend script, updaterPath, "UTF-8-RAW"

    parentPid := DllCall("GetCurrentProcessId")
    Run(
        'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "'
        updaterPath '" -ParentPid ' parentPid ' -CurrentExe "' A_ScriptFullPath '" -NewExe "' newExePath '"',
        ,
        "Hide"
    )
    ExitApp
}

CheckForUpdates(*) {
    global AppName, AppVersion, ReleaseBaseUrl, ReleaseExeName, UpdateCheckBusy, DataDir
    if (!A_IsCompiled || UpdateCheckBusy)
        return

    UpdateCheckBusy := true
    installRequested := false
    progressUi := ""
    try {
        metadata := ParseUpdateMetadata(HttpGetText(ReleaseBaseUrl "update.ini"))
        if (!metadata.Has("version") || !metadata.Has("sha256"))
            throw Error("The update metadata is incomplete.")

        latestVersion := metadata["version"]
        expectedHash := metadata["sha256"]
        if !RegExMatch(latestVersion, "^\d+\.\d+\.\d+$")
            throw Error("The release contains an invalid version.")
        if !RegExMatch(expectedHash, "i)^[0-9a-f]{64}$")
            throw Error("The release contains an invalid checksum.")
        if (VerCompare(latestVersion, AppVersion) <= 0)
            return

        choice := MsgBox(
            "A new version is available: v" latestVersion " (you have v" AppVersion ").`n`nDo you want to update now?",
            AppName " Update",
            "YesNo Icon?"
        )
        if (choice != "Yes")
            return

        installRequested := true
        progressUi := ShowUpdateProgressGui()
        newExePath := DataDir "\" ReleaseExeName ".update"
        DownloadBinaryWithProgress(
            ReleaseBaseUrl ReleaseExeName,
            newExePath,
            progressUi.status,
            progressUi.bar
        )
        progressUi.status.Text := "Verifying update..."
        Sleep(1)
        actualHash := GetFileSha256(newExePath)
        if (StrLower(actualHash) != StrLower(expectedHash)) {
            try FileDelete newExePath
            throw Error("Checksum mismatch. The update was discarded.")
        }

        progressUi.status.Text := "Installing update..."
        Sleep(1)
        StartSelfUpdate(newExePath)
    } catch as err {
        ; Being offline, rate-limited, or starting before the first release exists must never block
        ; normal macro use. Only surface an error after installation has begun.
        try {
            if IsObject(progressUi)
                progressUi.gui.Destroy()
        }
        if installRequested
            MsgBox(
                "The automatic update could not be completed.`n`n" err.Message,
                AppName " Update",
                "Icon!"
            )
    } finally {
        try {
            if IsObject(progressUi)
                progressUi.gui.Destroy()
        }
        UpdateCheckBusy := false
    }
}

JoinList(arr) {
    s := ""
    for v in arr
        s .= (s = "" ? "" : ",") v
    return s
}

; ============================================================
; WINDOW-RELATIVE COORDINATES (percent of the "opening")
; ============================================================
; The game window is always pinned into a fixed "opening" rectangle (Game Window tab). Every click
; position and detection-region corner is stored as a PERCENTAGE (0-100) of that opening rather
; than as a fixed screen pixel - so a preset keeps working if the opening is moved to another
; position/monitor or resized (a different resolution), instead of every coordinate breaking.
; These convert between an absolute screen pixel and that stored percentage. A zero-size opening
; (misconfigured) degrades gracefully by treating the value as a raw pixel.
;
; Note: the opening's OWN geometry (HoleX/Y/W/H) stays in absolute pixels - it's the reference
; frame everything else is measured against, so it can't be relative to itself.

; absolute screen X pixel -> stored percent-of-opening (3 decimals ~= 0.01px on a 1248px opening)
PctXFromAbs(absX) {
    hole := GetHoleRect()
    return (hole.w > 0) ? Round((absX - hole.x) / hole.w * 100, 3) : absX
}
PctYFromAbs(absY) {
    hole := GetHoleRect()
    return (hole.h > 0) ? Round((absY - hole.y) / hole.h * 100, 3) : absY
}

; stored percent-of-opening (either axis, parsed leniently) -> absolute screen {x, y} pixels
AbsXY(pctX, pctY) {
    hole := GetHoleRect()
    return {
        x: (hole.w > 0) ? Round(hole.x + SafeNum(pctX) / 100 * hole.w) : SafeInt(pctX),
        y: (hole.h > 0) ? Round(hole.y + SafeNum(pctY) / 100 * hole.h) : SafeInt(pctY)
    }
}

; ------------------------------------------------------------
; ONE-TIME MIGRATION: absolute-pixel coordinates -> percent-of-opening
; ------------------------------------------------------------
; Older configs stored every click/region coordinate as an absolute screen pixel. This converts
; them ONCE to percent-of-opening and stamps [General] CoordFormat=percent so it never runs again.
; It's exact/behavior-preserving at the current opening: because the game window is always pinned
; into the opening, an old absolute pixel = opening-origin + offset, so percent = (px-origin)/size
; reproduces the identical on-screen point. Type-aware - only real coordinate fields are touched
; (e.g. a "Zoom Out" step keeps a wheel-tick count in X, which must NOT be converted). Runs before
; any config value is read into the GUI, and uses the opening read straight from the config file
; (not the GUI controls, which don't exist yet at that point).

; Converts one coordinate key in place. `r` = the reference opening {x,y,w,h}. `isX` picks the axis.
MigConvertKey(section, key, isX, r) {
    global ConfigFile
    v := Cfg(section, key, "")
    if (v = "")
        return
    if isX
        IniWrite Round((SafeNum(v) - r.x) / r.w * 100, 3), ConfigFile, section, key
    else
        IniWrite Round((SafeNum(v) - r.y) / r.h * 100, 3), ConfigFile, section, key
}

; Converts a section's Map Advanced (Drag/Zoom Out) step coordinates. Normalizes any legacy
; Center-Camera/Zoom flags into the AdvStep format first (same call the app makes), then converts
; only the Drag steps' corners - a Zoom Out step keeps its tick count in X.
MigrateAdvStepCoords(section, r) {
    GetMapAdvSteps(section)
    n := SafeInt(Cfg(section, "AdvStepsCount", "0"))
    Loop n {
        i := A_Index
        if (Cfg(section, "AdvStep" i "Type", "Drag") = "Drag") {
            MigConvertKey(section, "AdvStep" i "X", true, r)
            MigConvertKey(section, "AdvStep" i "Y", false, r)
            MigConvertKey(section, "AdvStep" i "EndX", true, r)
            MigConvertKey(section, "AdvStep" i "EndY", false, r)
        }
    }
}

MigrateCoordsToPercent() {
    global ConfigFile, DataDir
    if (Cfg("General", "CoordFormat", "") = "percent")
        return

    r := {x: SafeInt(Cfg("General", "HoleX", "50")), y: SafeInt(Cfg("General", "HoleY", "50")),
        w: SafeInt(Cfg("General", "HoleW", "1248")), h: SafeInt(Cfg("General", "HoleH", "702"))}
    if (r.w <= 0 || r.h <= 0)
        return   ; opening not usable yet - retry next launch rather than convert against a bad frame

    ; Clearly-named safety copy of the pre-migration config, on top of the normal rotating backups.
    try {
        backupDir := DataDir "\config_backups"
        if !DirExist(backupDir)
            DirCreate backupDir
        if FileExist(ConfigFile)
            FileCopy ConfigFile, backupDir "\config_before_percent_" FormatTime(, "yyyyMMdd_HHmmss") ".ini", 1
    }

    ; [General]: after-place click, disconnect region + reconnect click, shared camera actions.
    MigConvertKey("General", "AfterPlaceClickX", true, r)
    MigConvertKey("General", "AfterPlaceClickY", false, r)
    MigConvertKey("General", "DisconnectX1", true, r)
    MigConvertKey("General", "DisconnectY1", false, r)
    MigConvertKey("General", "DisconnectX2", true, r)
    MigConvertKey("General", "DisconnectY2", false, r)
    MigConvertKey("General", "DisconnectReconnectX", true, r)
    MigConvertKey("General", "DisconnectReconnectY", false, r)
    MigrateAdvStepCoords("General", r)

    ; Each preset: 3 options (click + availability region), the Back button, and every step.
    for name in StrSplit(Cfg("Presets", "List", ""), ",") {
        if (name = "")
            continue
        section := "Preset_" name
        Loop 3 {
            i := A_Index
            MigConvertKey(section, "Option" i "X", true, r)
            MigConvertKey(section, "Option" i "Y", false, r)
            MigConvertKey(section, "Option" i "DetX", true, r)
            MigConvertKey(section, "Option" i "DetY", false, r)
            MigConvertKey(section, "Option" i "DetEndX", true, r)
            MigConvertKey(section, "Option" i "DetEndY", false, r)
        }
        MigConvertKey(section, "BackX", true, r)
        MigConvertKey(section, "BackY", false, r)

        Loop SafeInt(Cfg(section, "ScreenCount", "0")) {
            s := A_Index
            Loop SafeInt(Cfg(section, "Screen" s "StepCount", "0")) {
                prefix := "Screen" s "Step" A_Index
                stepType := Cfg(section, prefix "Type", "Button Click")
                if (stepType = "Button Click" || stepType = "Press Start Button" || stepType = "Restart Stage Button") {
                    MigConvertKey(section, prefix "X", true, r)
                    MigConvertKey(section, prefix "Y", false, r)
                } else if (stepType = "Drag" || stepType = "Detect Map" || stepType = "Round End Detection" || stepType = "Ingame Detection" || stepType = "Custom Detection") {
                    MigConvertKey(section, prefix "X", true, r)
                    MigConvertKey(section, prefix "Y", false, r)
                    MigConvertKey(section, prefix "EndX", true, r)
                    MigConvertKey(section, prefix "EndY", false, r)
                }
                ; Zoom Out (X=ticks) and Start/Option Select/Camera Setup/Place Towers/Wait: no coords.
            }
        }
    }

    ; Each map profile: up to 10 tower placements + this map's own camera actions (if custom).
    for name in StrSplit(Cfg("MapProfiles", "List", ""), ",") {
        if (name = "")
            continue
        section := "MapProfile_" name
        Loop 10 {
            i := A_Index
            MigConvertKey(section, "Placement" i "X", true, r)
            MigConvertKey(section, "Placement" i "Y", false, r)
        }
        MigrateAdvStepCoords(section, r)
    }

    IniWrite "percent", ConfigFile, "General", "CoordFormat"
}

; ============================================================
; MULTI-GAME SECTION NAMING
; ============================================================
; ActiveGameName is fixed for the life of this engine process (set once by InitGames, switching
; games is a config write plus an engine restart from gui/app/main_window.py, not a live reload),
; so every one of these can read the global directly instead of taking a game parameter.
GameSection() {
    global ActiveGameName
    return "Game_" ActiveGameName
}

GamePresetsListSection() {
    global ActiveGameName
    return "Game_" ActiveGameName "_Presets"
}

GamePresetSection(name) {
    global ActiveGameName
    return "Game_" ActiveGameName "_Preset_" name
}

GameMapProfilesListSection() {
    global ActiveGameName
    return "Game_" ActiveGameName "_MapProfiles"
}

GameMapProfileSection(name) {
    global ActiveGameName
    return "Game_" ActiveGameName "_MapProfile_" name
}

; Per-game keys that used to live directly in [General]: Timing, Tower Loadout, and the shared
; (non-custom-camera) map Advanced Steps. Everything else in [General] (Game Window, Disconnect,
; Remote Agent, CoordFormat/GameFormat) stays shared across every game - see the task note in
; tasklist/done/multi-game-support.md for why this split matches the user's own stated scope.
GeneralKeysMovedIntoGame() {
    keys := ["RoundWaitSeconds", "ClickDelayMs", "PlaceTowerDelayMs", "AfterPlaceClick",
        "AfterPlaceClickX", "AfterPlaceClickY", "MaxRounds", "MarkerSize", "NumPlacements",
        ; GetMapAdvSteps()'s own one-time-per-section migration marker plus the pre-AdvSteps legacy
        ; keys it migrates from - both need to move with the shared camera actions they describe,
        ; whichever form (pre- or post-migration) this config is currently in.
        "AdvStepsMigrated", "CenterCamera", "CamStartX", "CamStartY", "CamEndX", "CamEndY",
        "CamDragMs", "ZoomOut", "ZoomTicks"]
    Loop 10
        keys.Push("Slot" A_Index)
    advCount := SafeInt(Cfg("General", "AdvStepsCount", "0"))
    keys.Push("AdvStepsCount")
    Loop advCount {
        prefix := "AdvStep" A_Index
        keys.Push(prefix "Type", prefix "X", prefix "Y", prefix "EndX", prefix "EndY", prefix "DragMs")
    }
    return keys
}

; Wraps a pre-multi-game config's single implicit game into one [Game_<default>] section, ONCE,
; the same one-time-flag pattern as MigrateCoordsToPercent (guarded by [General] GameFormat, backs
; up config first). Must run AFTER MigrateCoordsToPercent (so it only ever has to move
; already-percent-format data) and BEFORE InitGames/InitMapProfiles/InitPresets (so those always
; find an already-game-scoped config, migrated or freshly created either way).
;
; On an existing pre-multi-game config this moves [Presets]/[Preset_*], [MapProfiles]/
; [MapProfile_*], and the per-game [General] keys above wholesale into one default game so nothing
; existing is lost. On a fresh install there is nothing to move - this just seeds an empty default
; game, and InitPresets/InitMapProfiles create their own usual first-run defaults inside it.
MigrateToGames() {
    global ConfigFile, DataDir
    if (Cfg("General", "GameFormat", "") = "v1")
        return

    try {
        backupDir := DataDir "\config_backups"
        if !DirExist(backupDir)
            DirCreate backupDir
        if FileExist(ConfigFile)
            FileCopy ConfigFile, backupDir "\config_before_games_" FormatTime(, "yyyyMMdd_HHmmss") ".ini", 1
    }

    defaultGame := "Anime Expedition"

    ; Phase 1: COPY everything into the new game-scoped sections. Deliberately no deletes yet - if
    ; the app is killed mid-copy, every old section is still fully intact, GameFormat is still not
    ; "v1", and the next launch simply redoes this phase (IniWrite overwrites, so re-copying is
    ; harmless). This is what makes the migration safe to interrupt at any point.
    for key in GeneralKeysMovedIntoGame() {
        value := Cfg("General", key, "")
        if (value != "")
            IniWrite value, ConfigFile, "Game_" defaultGame, key
    }

    presetNames := StrSplit(Cfg("Presets", "List", ""), ",")
    for name in presetNames {
        if (name = "")
            continue
        CopyIniSection("Preset_" name, "Game_" defaultGame "_Preset_" name)
    }
    if (Cfg("Presets", "List", "") != "") {
        IniWrite Cfg("Presets", "List", ""), ConfigFile, "Game_" defaultGame "_Presets", "List"
        IniWrite Cfg("Presets", "Active", ""), ConfigFile, "Game_" defaultGame "_Presets", "Active"
    }

    mapNames := StrSplit(Cfg("MapProfiles", "List", ""), ",")
    for name in mapNames {
        if (name = "")
            continue
        CopyIniSection("MapProfile_" name, "Game_" defaultGame "_MapProfile_" name)
    }
    if (Cfg("MapProfiles", "List", "") != "") {
        IniWrite Cfg("MapProfiles", "List", ""), ConfigFile, "Game_" defaultGame "_MapProfiles", "List"
        IniWrite Cfg("MapProfiles", "Active", ""), ConfigFile, "Game_" defaultGame "_MapProfiles", "Active"
    }

    IniWrite defaultGame, ConfigFile, "Games", "List"
    IniWrite defaultGame, ConfigFile, "Games", "Active"

    ; Phase 2: only now, with every new section confirmed written, mark the migration complete.
    ; From this point on every future launch skips straight past this whole function.
    IniWrite "v1", ConfigFile, "General", "GameFormat"

    ; Phase 3: best-effort cleanup of the old sections. If THIS gets interrupted, the worst case is
    ; harmless leftover old-format sections sitting unread forever (GameFormat=v1 already guards
    ; every future launch against re-running this function) - never data loss.
    for key in GeneralKeysMovedIntoGame()
        try IniDelete ConfigFile, "General", key
    for name in presetNames {
        if (name != "")
            try IniDelete ConfigFile, "Preset_" name
    }
    try IniDelete ConfigFile, "Presets"
    for name in mapNames {
        if (name != "")
            try IniDelete ConfigFile, "MapProfile_" name
    }
    try IniDelete ConfigFile, "MapProfiles"
}

; Copies every key of `fromSection` to `toSection` (both in ConfigFile), key-by-key so unknown/
; future keys survive the copy the same way MigrateCoordsToPercent's per-key approach does.
CopyIniSection(fromSection, toSection) {
    global ConfigFile
    try keysStr := IniRead(ConfigFile, fromSection)
    catch {
        return   ; section does not exist - nothing to copy (e.g. a preset with no ScreenCount yet)
    }
    for line in StrSplit(keysStr, "`n") {
        eqPos := InStr(line, "=")
        if !eqPos
            continue
        key := SubStr(line, 1, eqPos - 1)
        value := SubStr(line, eqPos + 1)
        IniWrite value, ConfigFile, toSection, key
    }
}

; Sets a DropDownList's selection to `value`, falling back to `fallback` (or, failing that too,
; leaving whatever was already selected) instead of throwing "Invalid value" - which AHK raises
; whenever the assigned text doesn't exactly match one of the control's current items. This can
; happen with perfectly valid saved data whenever the control's item list hasn't caught up yet
; (e.g. a step imported from another preset whose On True/On False points at a screen name that
; doesn't exist here) - a hard crash on stale/foreign data is worse than silently falling back.

; ============================================================
; ADVANCED DETECTION OUTCOMES (serialization helpers)
; ============================================================
; A "Custom Detection" step with Advanced checked stores its named outcomes as a single flattened
; string (fits into one stepsLV column / one ini value, same as every other step field) instead of
; a proper nested structure - "Name=Screen|Name=Screen|...". Names/screen values aren't expected to
; contain "|" or "=" in practice (screen names are picked from a dropdown; outcome names are short
; OCR expected-text labels), so this is deliberately simple rather than fully escaped.
SerializeOutcomes(outcomes) {
    s := ""
    for o in outcomes
        s .= (s = "" ? "" : "|") o.Name "=" o.Screen
    return s
}

ParseOutcomes(s) {
    outcomes := []
    if (s = "")
        return outcomes
    for part in StrSplit(s, "|") {
        eqPos := InStr(part, "=")
        if !eqPos
            continue
        outcomes.Push({Name: SubStr(part, 1, eqPos - 1), Screen: SubStr(part, eqPos + 1)})
    }
    return outcomes
}

; ============================================================
; PER-OPTION DAILY USAGE (Option Select challenge limits)
; ============================================================
; Each option's "used today" counter is stored alongside the date it was last touched, so it
; auto-resets the first time it's read/written on a new day - no separate midnight timer needed.
TodayStamp() {
    return FormatTime(, "yyyyMMdd")
}

; Returns option i's still-valid "used today" count for the given preset ini section (0 if the
; stored count belongs to an earlier day).
GetOptionUsedToday(section, i) {
    storedDate := Cfg(section, "Option" i "UsedDate", "")
    if (storedDate != TodayStamp())
        return 0
    return SafeInt(Cfg(section, "Option" i "UsedCount", "0"))
}

SetOptionUsedToday(section, i, count) {
    global ConfigFile
    IniWrite Max(0, count), ConfigFile, section, "Option" i "UsedCount"
    IniWrite TodayStamp(), ConfigFile, section, "Option" i "UsedDate"
}

; Bumps option i's "used today" count for `presetName` by one (called once an Option Select step
; actually commits to playing that option) and returns the new count.
IncrementOptionUsed(presetName, i) {
    section := GamePresetSection(presetName)
    newCount := GetOptionUsedToday(section, i) + 1
    SetOptionUsedToday(section, i, newCount)
    return newCount
}

; Refreshes the Preset Settings tab's "Today's Challenge Usage" rows for `name` - option names/max
; mirrored from OptData (already loaded by the time this is called from LoadPreset/SavePresetToIni),
; used-today counts read fresh from ini (auto-resetting on a new day, see GetOptionUsedToday).

; True if the preset has at least one "Option Select" step in any of its screens - i.e. it's a
; challenge-style preset whose daily option usage is meaningful.

; Shows the "Today's Challenge Usage" group only for presets that actually use an Option Select
; step; hides it entirely for everything else (where the 3 option counters mean nothing).

; Persists a manual edit to one of the Preset Settings tab's "used today" fields immediately -
; these are daily counters, not "click Save to keep it" config, so they save on every change.

; Persists a manual edit to one of the Preset Settings tab's daily-limit fields immediately, and
; mirrors it into OptData's MaxEdit (the same field shown in Edit Preset > Option > Max) so both
; stay in sync regardless of which one was just edited.

; ============================================================
; GLOBAL STATE
; ============================================================
Running := false
Paused := false
DryRun := false          ; "test mode": walk the preset and LOG every action, but skip the actual
                          ; clicks/keypresses/drags - for safely watching what a preset WOULD do.
                          ; Read from dryRunChk at StartMacro time; not persisted (always off on launch).
RegionPreviewGui := ""   ; translucent overlay that briefly highlights an OCR region on screen
PointPreviewGui := ""    ; translucent overlay that briefly highlights a point on screen
CaptureTarget := ""      ; "active" while a position capture is in progress
CaptureXCtrl := ""
CaptureYCtrl := ""
FieldCaptureId := ""      ; non-empty while a Python field-id point capture is awaiting F8/Escape
FieldCaptureRestoreGui := false  ; true if MyGui was actually visible before BeginFieldCapture hid it
OptData := []             ; 3 option objects
OptionSectionControls := [] ; every control in the "challenge options" section (EditGui), shown only while editing an "Option Select" step
PlaceData := []            ; up to 10 placement objects (coords per map + custom slot override)
GeneralSlotDdls := []       ; the 10 default tower-slot dropdowns (General tab, shared across maps)
PresetNames := []          ; names of all routine presets
CurrentPresetName := ""
CurrentScreenName := ""    ; which screen is currently shown in the step editor
PresetScreens := []        ; [{Name, Steps}, ...] for the running macro, built at StartMacro time
EditGuiVisible := false    ; whether the Edit Preset window is currently shown (set by Open/CloseEditGui)
RunningPresetName := ""    ; the preset actually being executed by the running macro (set at StartMacro time)
RunningScreenName := ""    ; the screen currently executing (set by MainLoop each iteration) - used to
                             ; keep the Edit Preset window's screen/step selection following along live
MapProfileNames := []      ; names of all map profiles (one per map)
CurrentMapProfileName := ""
GameNames := []            ; names of all games (each with its own presets/map profiles/timing settings)
ActiveGameName := ""       ; the game whose data every Preset_/MapProfile_ section and Timing/Tower Loadout/
                             ; AdvStep* key resolves under - set once at startup (InitGames), fixed for the
                             ; life of this engine process. Switching games is a config write plus an engine
                             ; restart (gui/app/main_window.py), not a live in-place reload.
OverlayGuis := []          ; the 4 gray overlay bar windows
OverlayVisible := false
; Fixed for this engine process lifetime; suppresses the on-screen overlay in background sessions.
InBackgroundWindowsSession := DetectBackgroundWindowsSession()
LockedProcess := ""        ; exe name of the window currently locked into the opening
GameWindowLeftToGame := false   ; the most recent ForceGameWindow left this window's geometry to the
                                ; game itself (background session, see LeaveGameWindowGeometryAlone).
                                ; What ACTUALLY happened, not what policy allowed: the fallback there
                                ; positions the window anyway when the game did not come up filling
                                ; the opening. Reporting only, and per ATTEMPT rather than per run,
                                ; which is why nothing enforcing may read it: see EnforceWindowLock.
MarkerGui := ""             ; red dot marker shown during position capture
LastDetectedMap := ""       ; map name found by the most recent "Detect Map" step (map banner is often
                             ; only visible on the selection screen, not once you're already in the round)
LogGui := ""                 ; log panel window shown in the gray area right of the game window
LogEdit := ""                 ; the read-only multi-line Edit control inside LogGui
LogLines := []                ; recent log lines (capped), mirrored into LogEdit when it exists
TimeBreakdownGui := ""         ; "Screen Time" table panel shown below LogGui, in the same gray column -
                               ; replaces the old plain-text "Screen Run Counts" box
ScreenTimeLV := ""             ; ListView inside TimeBreakdownGui: one row per screen, cumulative time
ScreenTimeMs := Map()          ; screen name -> cumulative ms spent on that screen so far THIS run -
                               ; resets every MainLoop() call, same scope as ScreenRunCounts
ScreenEnterTick := 0           ; Now64() when the currently running screen was entered, used to
                               ; flush the previous screen's elapsed time into ScreenTimeMs on the next switch
StepTimeMs := Map()            ; "Screen - Type (Label)" -> cumulative ms across every completed attempt
                               ; at that step so far THIS run - resets every MainLoop() call. Each entry
                               ; to RunSteps' step loop body (including a step repeating itself via
                               ; "(Repeat)") counts as one attempt/repetition
CurrentStepKey := ""           ; key of the step attempt currently in progress (see StepTimeMs), used to
                               ; flush its elapsed time on the next step-loop entry and to compute its
                               ; live "current repetition" time
StepCurrentStartTick := 0      ; Now64() when CurrentStepKey's current attempt started
SessionId := ""                ; opaque id regenerated every time the below counters reset (every
                               ; MainLoop() call, i.e. every run start including internal restarts) -
                               ; lets the remote backend detect a session boundary and archive the
                               ; previous session's last-known stats as history
SessionStartTick := 0          ; Now64() when the current session (see SessionId) began
StatsGui := ""                ; "Application Stats" panel shown below LogGui in the same gray area
StatsMapText := ""             ; text controls inside StatsGui, one per stat row (see RenderStatsPanel)
StatsScreenText := ""
StatsStepText := ""
StatsStepRepeatText := ""
StatsStartRepeatText := ""
StatsVictoryText := ""
StatsDefeatText := ""
StatsSessionTimeText := ""
StatsCurrentStepTimeText := ""
StatsLastVals := Map()        ; last value pushed to each stats control (keyed by field) - lets
                               ; RenderStatsPanel (called every step) skip control updates whose value
                               ; didn't actually change, avoiding needless WM_SETTEXT/repaint churn
ScreenRepeatCount := 0        ; screen-repetitions (returns to the Start screen) so far THIS run -
                               ; resets every MainLoop() call; was called "Cycle Count"
StepRepeatCount := 0          ; how many times any step's On True/On False resolved to "(Repeat)"
                               ; so far THIS run - resets every MainLoop() call, same scope as ScreenRepeatCount
StartRepeatCount := 0         ; lifetime count of screen-repetitions across the whole session - same
                               ; event as ScreenRepeatCount, just never reset by MainLoop(), so it
                               ; keeps counting across an internal restart (disconnect auto-reconnect,
                               ; a committed queued preset switch). Zeroed once per genuine new Start
                               ; (F10 / the local IPC bridge's START command) in StartMacro().
VictoryCount := 0             ; lifetime count of OCR scans whose RECOGNIZED text contained "Victory"
DefeatCount := 0              ; lifetime count of OCR scans whose RECOGNIZED text contained "Defeat" -
                               ; both come from any Round End/Ingame/Custom Detection step's scan
                               ; (matched or not) - see TrackVictoryDefeat(). Same reset scope as
                               ; StartRepeatCount above: survives an internal restart, zeroed only on
                               ; a genuine new Start in StartMacro().
RunningStepDescription := ""  ; "Type (Label)" of the step currently executing, for the stats panel
HoverTooltipMap := Map()      ; Hwnd -> tooltip text, for "?" help icons
LastHoverHwnd := 0            ; Hwnd currently showing its tooltip (0 = none)
MapAdvStepsDoneThisCycle := false ; the map's Drag/Zoom Out actions run at most once per cycle,
                                   ; reset whenever a "Detect Map" step runs again (new round)
UsageNameTexts := []          ; Preset Settings tab: option name labels (mirror OptData's NameEdit)
UsageUsedEdits := []          ; Preset Settings tab: editable "used today" count per option
UsageMaxEdits := []           ; Preset Settings tab: editable daily limit per option (mirrors/writes OptData's MaxEdit)
DisconnectRestartPending := false ; set by CheckDisconnectTick when a disconnect was found; StartMacro loops back
                                   ; to the beginning of the current preset (once MainLoop returns) when this is true
DisconnectCheckBusy := false      ; guards against an overlapping disconnect OCR scan if one ever takes longer than the timer period
DisconnectLastCheckTick := 0      ; A_TickCount of the last disconnect OCR scan, used to honor the configurable check interval
remoteBridgeChk := ""             ; the "Enable remote bridge" checkbox - the live on/off source for remote_bridge.ahk
                                   ; (like disconnectEnabledChk drives CheckDisconnectTick), persisted to [General] RemoteBridgeEnabled
PendingPresetSwitch := ""         ; preset name queued via the remote QUEUE_PRESET command (empty = none). MainLoop commits it at
                                   ; the next cycle boundary; only ever set to a name that already exists (validated before storing).
PresetSwitchRestartPending := false ; set by MainLoop at a cycle boundary when a queued preset switch is committed - makes StartMacro
                                     ; restart into PendingPresetSwitch, reusing the same restart path as DisconnectRestartPending. Set
                                     ; ONLY at the boundary (never by STOP), so stopping never gets mistaken for a switch.
StopRequested := false            ; latched true by any manual stop (Escape / remote STOP). StartMacro checks it - atomically - right
                                   ; before it would (re)start a run, so a stop that arrives during the restart/reload prep window (e.g.
                                   ; during ForceGameWindow's Sleep, after MainLoop already returned for a disconnect or preset-switch
                                   ; restart) is honored, instead of being overridden by the loop re-setting Running:=true. Reset at
                                   ; StartMacro entry.
MacroActive := false              ; true while a StartMacro session is live - INCLUDING the brief prep windows where Running is
                                   ; momentarily false (initial startup, or a disconnect/preset-switch restart between MainLoop
                                   ; returning and Running:=true). Lets a remote STOP tell "genuinely idle" (reject) apart from
                                   ; "mid-prep, so the stop latch will take effect" (acknowledge as stopping).
EditingOutcomes := []              ; the "Custom Detection" step currently shown in the Step Editor's Advanced
                                   ; Detection outcomes (array of {Name, Screen}) - pre-commit, mirrors every
                                   ; other step-editor field until "Add Step"/"Update Selected" is clicked
OcrServerPid := 0                  ; PID of the persistent OCR helper (ocr_server.exe) - 0 when not running.
                                   ; One long-lived process loads the .NET/WinRT OCR assemblies ONCE and then
                                   ; services every scan, instead of paying ~0.5s of powershell.exe startup per
                                   ; call (see EnsureOcrServer/RunOcrOnRegion).
OcrBenchmarkPid := 0               ; PID of the optional experimental OCR benchmark helper
                                   ; (ocr_benchmark.exe) - 0 when not running or not present. Only exists on an
                                   ; experimental build the user has unzipped into RuntimeDir\ocr_benchmark; a
                                   ; normal production install never has this file, so EnsureOcrBenchmark() is a
                                   ; harmless no-op there (see EnsureOcrBenchmark).
HelperJobHandle := 0               ; handle of the Windows job object every helper process the engine spawns is
                                   ; assigned to - 0 until the first helper is started (see EnsureHelperJob).
                                   ; Held open for this process's whole lifetime on purpose: closing the last
                                   ; handle to it is what terminates the helpers when the engine dies.
OcrReqToken := 0                   ; incrementing request id, so a response can be matched to its request and a
                                   ; stray/stale response file is never mistaken for the current answer
OcrBusy := false                   ; true while the main thread is mid OCR request - CheckDisconnectTick checks
                                   ; this and skips its own scan rather than clashing over the request/response files
StepRows := []                     ; source-of-truth array of step objects for the screen currently open in the
                                   ; step editor. stepsLV is a rendered VIEW of this (see RenderStepsLV/StepDisplayCells):
                                   ; the table only shows the columns each step type actually uses, but every field
                                   ; (incl. hidden ones like a Logic step's OCR region) lives here and round-trips to ini.
ActivePresetName := ""             ; the preset that actually runs on Start/F10 - chosen via the "Set as Active" button,
                                   ; independent of which preset is currently selected/being edited (CurrentPresetName).
                                   ; Persisted as [Presets] Active. StartMacro switches the view to it before running.
activePresetText := ""             ; the "Runs on Start: <name>" indicator label (Preset Settings tab)
setActiveBtn := ""                 ; the "Set as Active" button
UsageBoxControls := []             ; every control in the "Today's Challenge Usage" group (Preset Settings tab) - shown
                                   ; only while a preset that actually uses an "Option Select" step is selected
RegionCapActive := false           ; true while a snipping-tool-style OCR region rectangle capture is in progress
RegionCapPhase := 0                ; 0 = waiting for the first click, 1 = dragging the rectangle
RegionCapStartX := 0
RegionCapStartY := 0
RegionCapTargets := []             ; [x1Ctrl, y1Ctrl, x2Ctrl, y2Ctrl] edit fields the captured rect writes into
RegionCapFieldIds := []            ; [x1, y1, x2, y2] Python field IDs; non-empty routes the result to local_capture_result.txt
RegionCapRestore := []             ; windows hidden for the duration of the capture, re-shown on finish/cancel
RegionDimGui := ""                 ; the dim full-screen overlay shown during region capture
RegionBandGuis := []               ; the 4 red bars forming the live rubber-band rectangle
StepDragFrom := 0                  ; row a step-list drag-reorder started on (0 = not dragging)
StepDragging := false

; Shows the window prefilled with the remembered agent path/server URL/email (or a sensible default -
; the bundled release copy, or a built dev/source checkout - see DefaultRemoteAgentPath) and a fresh
; status line. The password and
; 2FA code are never remembered, and the mode always resets to "Log in".


; A release build bundles animeexpedition-agent.exe next to the installed app (extracted by
; EnsureBundledRuntimeFiles on every startup, same mechanism as the OCR helper), so that is
; checked first. A dev/source checkout instead keeps remote/agent as a sibling of macro/ - if it
; has already been built there (per remote/README.md's `go build`), fall back to that so a
; developer never has to Browse by hand. If neither exists yet, this returns "" and the field
; starts empty until the user Browses once (the choice is then remembered in config.ini).
DefaultRemoteAgentPath() {
    global RuntimeDir
    bundledPath := RuntimeDir "\animeexpedition-agent.exe"
    if FileExist(bundledPath)
        return bundledPath
    devPath := A_ScriptDir "\..\remote\agent\animeexpedition-agent.exe"
    return FileExist(devPath) ? devPath : ""
}


; The base filename of whatever path is currently set (e.g. "animeexpedition-agent.exe", or
; whatever the user actually renamed/selected) - falls back to the documented default name only
; while the field is still empty, so detection/start/stop always target the SAME exe the user
; configured instead of a hardcoded name that could silently stop matching a renamed binary.
RemoteAgentExeName(agentPath) {
    path := Trim(agentPath)
    if (path = "")
        return "animeexpedition-agent.exe"
    SplitPath path, &name
    return (name != "") ? name : "animeexpedition-agent.exe"
}

; Detects the agent by executable name rather than a remembered PID, so status is correct even
; right after this app restarts - the agent is meant to keep running independently (see the Start/
; Stop help icon above), so nothing here tracks "the PID we personally launched".
RemoteAgentRunningPid(agentPath) {
    return ProcessExist(RemoteAgentExeName(agentPath))
}


; Launches the agent hidden in the background (long-poll mode - no --login/--register, so it uses
; the device token just saved by pairing) and does a brief liveness check, since a not-yet-paired or
; misconfigured agent exits almost immediately. Shared by LocalBridgeStartRemoteAgent (local_bridge.ahk)
; and LocalBridgePairRemoteAgent right after a successful pairing.
RemoteAgentAutoStart(agentPath) {
    agentPath := Trim(agentPath)
    if RemoteAgentRunningPid(agentPath)
        return "Agent already running."
    if (agentPath = "" || !FileExist(agentPath))
        return "Set a valid path to animeexpedition-agent.exe first (Browse...)."
    try {
        Run(WinArgQuote(agentPath), , "Hide")
    } catch as err {
        return "Could not start the agent: " err.Message
    }
    Sleep 300   ; give it a moment to fail fast (e.g. not paired yet) before reporting success
    if !RemoteAgentRunningPid(agentPath)
        return "The agent exited immediately - make sure it is paired first."
    LogMsg("Remote agent: started.")
    return "Agent started."
}



; Populate GameNames/ActiveGameName, then MapProfileNames/PresetNames (plus run their one-time
; legacy migrations) from config.ini. All plain data the engine and the bridges validate against
; (PresetIndex, MapProfileNames membership checks) - the native editor GUI these used to also
; populate is gone. InitGames must run first: everything after it resolves section names through
; GameSection()/GamePresetSection()/GameMapProfileSection(), which read ActiveGameName.
InitGames()
InitMapProfiles()
InitPresets()
CreateMarker()

; ============================================================
; GAME MANAGEMENT (which game's presets/map profiles/timing settings are active)
; ============================================================
; Populates GameNames and resolves ActiveGameName once at startup, fixed for the life of this
; engine process - switching games (gui/app/main_window.py) writes [Games] Active in config.ini
; and then restarts the engine process, rather than reloading the active game live. MigrateToGames()
; guarantees [Games] List/Active are always non-empty by the time this runs, even on a config that
; had nothing to migrate (a fresh install), so the only remaining defensive case here is an Active
; value that no longer names a real game (e.g. hand-edited config.ini) - same fallback InitPresets()
; uses for ActivePresetName.
InitGames() {
    global ConfigFile, GameNames, ActiveGameName

    listStr := Cfg("Games", "List", "")
    if (listStr = "") {
        ; Defense in depth only: MigrateToGames() always sets this before InitGames() runs. A
        ; missing [Games] List here means config.ini was hand-edited or predates this migration
        ; entirely (should not happen given call order in the script's top-level code, section
        ; "ONE-TIME CONFIG MIGRATIONS" above) - fall back to a single default game rather than
        ; crashing every read that follows.
        listStr := "Anime Expedition"
        IniWrite listStr, ConfigFile, "Games", "List"
        IniWrite listStr, ConfigFile, "Games", "Active"
    }
    GameNames := StrSplit(listStr, ",")

    active := Cfg("Games", "Active", "")
    found := false
    for n in GameNames {
        if (n = active) {
            found := true
            break
        }
    }
    if !found {
        active := GameNames[1]
        IniWrite active, ConfigFile, "Games", "Active"
    }
    ActiveGameName := active
}

; ============================================================
; MAP PROFILE MANAGEMENT (placement coordinates, auto-detected per map)
; ============================================================
InitMapProfiles() {
    global ConfigFile, MapProfileNames

    listStr := Cfg(GameMapProfilesListSection(), "List", "")

    ; One-time migration: earlier versions stored NumPlacements/slots per map profile.
    ; If this game's section doesn't have them yet, lift them from whichever profile has them.
    if (Cfg(GameSection(), "NumPlacements", "") = "") {
        legacySource := ""
        if (listStr != "") {
            candidates := StrSplit(listStr, ",")
            for n in candidates {
                if (Cfg(GameMapProfileSection(n), "NumPlacements", "") != "") {
                    legacySource := n
                    break
                }
            }
        }
        if (legacySource != "") {
            IniWrite Cfg(GameMapProfileSection(legacySource), "NumPlacements", "4"), ConfigFile, GameSection(), "NumPlacements"
            Loop 10 {
                i := A_Index
                IniWrite Cfg(GameMapProfileSection(legacySource), "Placement" i "Slot", "1"), ConfigFile, GameSection(), "Slot" i
            }
        } else {
            IniWrite "4", ConfigFile, GameSection(), "NumPlacements"
            Loop 10 {
                i := A_Index
                IniWrite Cfg("Placement" i, "Slot", "1"), ConfigFile, GameSection(), "Slot" i
            }
        }
    }

    if (listStr = "") {
        ; First run: migrate the old single placement config (if any) into a "Default" profile
        IniWrite "", ConfigFile, GameMapProfileSection("Default"), "ExpectedText"
        IniWrite 0, ConfigFile, GameMapProfileSection("Default"), "CustomTowers"
        Loop 10 {
            i := A_Index
            IniWrite Cfg("Placement" i, "X", "0"), ConfigFile, GameMapProfileSection("Default"), "Placement" i "X"
            IniWrite Cfg("Placement" i, "Y", "0"), ConfigFile, GameMapProfileSection("Default"), "Placement" i "Y"
        }
        IniWrite "Default", ConfigFile, GameMapProfilesListSection(), "List"
        IniWrite "Default", ConfigFile, GameMapProfilesListSection(), "Active"
        listStr := "Default"
    }

    MapProfileNames := StrSplit(listStr, ",")
}

; Keeps the "Default Map" dropdown (Preset Settings tab) in sync with the current list of
; map profiles. Always offers "(none)" so detection can be required with no fallback.



; Loads the map-actions ListView (Advanced Settings) from whichever section is currently in
; effect for `name` - its own section if "custom" is checked, otherwise [General]. Does NOT touch
; mapCustomCameraChk itself, so it's safe to call right after the user toggles it.


; Snapshots the Map Profile editor's control values as plain data for SaveMapProfileToIni().

; Writes one map profile's own fields from explicit plain data. Camera/zoom steps are deliberately
; saved separately by GUI callers through SaveMapAdvStepsFromLV(), so IPC callers need not touch a ListView.



; Creates a map profile from an explicit name and returns a bridge-friendly result. The default
; profile data is constructed directly (not read back from the map-profile controls); those
; controls are still written afterward so the legacy GUI stays synchronized for display. Only
; prompting and destructive confirmation stay in the Click wrappers.


; Renames a map profile using explicit old/new names. It intentionally retains the legacy GUI
; snapshot and control refreshes; callers that need a prompt or dialog use RenameMapProfileClick().


; Deletes the explicit map profile without a confirmation dialog. The wrapper retains the legacy
; last-profile guard and Yes/No confirmation, while direct callers receive the same guard result.


; ============================================================
; MAP DETECTION VIA OCR (Windows.Media.Ocr, same engine as PowerToys Text Extractor)
; ============================================================
; Builds a {x,y,w,h} rect from a step's own Region1 (X,Y) / Region2 (EndX,EndY) fields - every
; Logic step (Detect Map / Round End Detection / Ingame Detection) carries its own region now,
; instead of there being one shared region per detection kind.
RectFromStep(step) {
    ; step.X/Y and step.EndX/EndY are the two region corners, stored as percent-of-opening.
    a := AbsXY(step.X, step.Y)
    b := AbsXY(step.EndX, step.EndY)
    return {x: Min(a.x, b.x), y: Min(a.y, b.y), w: Abs(b.x - a.x), h: Abs(b.y - a.y)}
}

; ============================================================
; OCR REGION LIVE PREVIEW
; ============================================================
; Briefly outlines the given absolute-pixel rect on screen (a bright, click-through, hollow border)
; so you can visually confirm which area a detection region actually covers - handy when dialing in
; Region1/Region2 for a step, an option Availability Check, or Disconnect Detection. Auto-hides
; after ~2.5s. `rect2` is the two percent corners {x1,y1,x2,y2} straight from the edit fields.
ShowRegionPreview(rect) {
    global RegionPreviewGui
    if (rect.w <= 0 || rect.h <= 0) {
        MsgBox "Set both Region1 and Region2 positions first."
        return
    }
    HideRegionPreview()
    RegionPreviewGui := []
    t := 3   ; border thickness (px) - a hollow outline so the content inside stays visible
    bars := [
        {x: rect.x - t, y: rect.y - t, w: rect.w + 2 * t, h: t},        ; top
        {x: rect.x - t, y: rect.y + rect.h, w: rect.w + 2 * t, h: t},   ; bottom
        {x: rect.x - t, y: rect.y, w: t, h: rect.h},                    ; left
        {x: rect.x + rect.w, y: rect.y, w: t, h: rect.h}               ; right
    ]
    for b in bars {
        g := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x20 +E0x08000000")  ; E0x20 = click-through
        g.BackColor := "FF2A2A"
        g.Show("x" b.x " y" b.y " w" b.w " h" b.h " NoActivate")
        RegionPreviewGui.Push(g)
    }
    SetTimer HideRegionPreview, -2500
}
HideRegionPreview() {
    global RegionPreviewGui
    if (RegionPreviewGui != "") {
        for g in RegionPreviewGui
            try g.Destroy()
    }
    RegionPreviewGui := ""
}

; Briefly marks the given absolute-pixel point on screen with a bright, click-through crosshair.
ShowPointPreview(pt) {
    global PointPreviewGui
    HidePointPreview()
    PointPreviewGui := []
    t := 3
    arm := 12
    bars := [
        {x: pt.x - arm, y: pt.y - 1, w: arm * 2, h: t},
        {x: pt.x - 1, y: pt.y - arm, w: t, h: arm * 2}
    ]
    for b in bars {
        g := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x20 +E0x08000000")  ; E0x20 = click-through
        g.BackColor := "FF2A2A"
        g.Show("x" b.x " y" b.y " w" b.w " h" b.h " NoActivate")
        PointPreviewGui.Push(g)
    }
    SetTimer HidePointPreview, -2500
}
HidePointPreview() {
    global PointPreviewGui
    if (PointPreviewGui != "") {
        for g in PointPreviewGui
            try g.Destroy()
    }
    PointPreviewGui := ""
}

; Returns the Windows job object that helper processes are put into, creating it on first use, or 0
; if it could not be created. The job is configured with JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE and its
; handle is then deliberately never closed: Windows terminates every process still in a job the
; moment its last handle goes away, and this process holding that one handle means "the engine is
; gone" and "the job closes" are the same event. That is what makes an orphaned helper structurally
; impossible instead of merely unlikely - it also covers the exits no code of ours can observe, a
; taskkill /F (which the GUI's own shutdown path escalates to, see stop_engine in
; gui/app/engine_process.py) and a hard crash, neither of which runs OnExit. ReapHelperProcesses is
; the graceful counterpart that lets a helper shut itself down cleanly first.
EnsureHelperJob() {
    global HelperJobHandle
    if HelperJobHandle
        return HelperJobHandle

    handle := 0
    try handle := DllCall("kernel32\CreateJobObjectW", "Ptr", 0, "Ptr", 0, "Ptr")
    if !handle
        return 0

    ; JOBOBJECT_EXTENDED_LIMIT_INFORMATION, whose first member is a JOBOBJECT_BASIC_LIMIT_INFORMATION.
    ; Its LimitFlags field sits at offset 16 on both architectures (two 8-byte LARGE_INTEGERs come
    ; first); only the total struct size differs, 144 bytes on x64 and 112 on x86. Information class
    ; 9 is JobObjectExtendedLimitInformation, and 0x2000 is JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
    info := Buffer(A_PtrSize = 8 ? 144 : 112, 0)
    NumPut("UInt", 0x2000, info, 16)
    ok := 0
    try ok := DllCall("kernel32\SetInformationJobObject", "Ptr", handle, "Int", 9, "Ptr", info
        , "UInt", info.Size, "Int")
    if !ok {
        try DllCall("kernel32\CloseHandle", "Ptr", handle)
        return 0
    }

    HelperJobHandle := handle
    return handle
}

; Puts a just-started helper process into that job. Best-effort by design: every failure here (no
; job, a process that already exited, a denied OpenProcess) only costs the hard-kill backstop, never
; the helper itself, so callers deliberately ignore the result and keep running.
;
; Descendants of an assigned process join the job automatically, which is what covers the second PID
; of a PyInstaller onefile helper (bootloader plus extracted child). There is a theoretical race,
; since AHK's Run cannot create a process suspended: a bootloader that spawned its child before this
; assignment lands would leave that child outside the job. In practice the bootloader first unpacks
; its whole archive to a temp directory, which takes orders of magnitude longer than the two DllCalls
; below, and the graceful path force-kills with taskkill /T anyway.
AssignHelperToJob(pid) {
    if !pid
        return false
    job := EnsureHelperJob()
    if !job
        return false

    ; PROCESS_TERMINATE (0x0001) | PROCESS_SET_QUOTA (0x0100) is the access AssignProcessToJobObject
    ; requires, and nothing more.
    processHandle := 0
    try processHandle := DllCall("kernel32\OpenProcess", "UInt", 0x0101, "Int", 0, "UInt", pid, "Ptr")
    if !processHandle
        return false

    assigned := 0
    try assigned := DllCall("kernel32\AssignProcessToJobObject", "Ptr", job, "Ptr", processHandle, "Int")
    try DllCall("kernel32\CloseHandle", "Ptr", processHandle)
    if !assigned {
        ; Logged rather than swallowed: this helper is now running WITHOUT the hard-kill backstop, so
        ; if orphaned helpers are ever reported again, the log says straight away whether the backstop
        ; was in place at all instead of the next session having to rediscover it.
        try LogMsg("Warning: helper PID " pid " could not be put into the kill-on-exit job object.")
        return false
    }
    return true
}

; Force-kills a process and everything it spawned, without letting a wedged taskkill.exe hang the
; caller. RunWait has no timeout of its own, and this runs from the exit path, where AutoHotkey's own
; guidance is that an exit callback finishes quickly (and where the GUI force-kills this engine after
; one second anyway) - an unbounded wait there would trade one hang for another.
KillProcessTree(pid, timeoutMs := 1000) {
    if !pid
        return
    killerPid := 0
    try Run('taskkill.exe /F /T /PID ' pid, , "Hide", &killerPid)
    catch
        return
    waited := 0
    while (waited < timeoutMs && killerPid && ProcessExist(killerPid)) {
        Sleep 25
        waited += 25
    }
}

; Runs on every exit AHK can observe: ExitApp from any of this script's error paths, the WM_CLOSE the
; GUI's graceful shutdown request sends (see stop_engine in gui/app/engine_process.py), and a Windows
; logoff/shutdown. Registered once at startup rather than wired into a single exit path, because the
; engine has many of them and each one used to leak the helpers: StopOcrServer() has always existed
; but nothing ever called it, so a normally closed app left its ocr_server.exe running indefinitely.
;
; Every step of it is bounded, because an exit callback that can hang holds the whole exit open: per
; helper, 600ms of grace for it to notice its stop file (the measured graceful path is ~450ms) plus
; at most 1000ms for the force-kill, so ~1.6s worst case on a normal install and ~3.2s on an
; experimental one that also runs the benchmark helper. Anything still alive after that is caught by
; the job object instead.
ReapHelperProcesses(exitReason, exitCode) {
    try StopOcrServer()
    try StopOcrBenchmark()
    ; The game outlives this process, so a window whose title bar was stripped for the fullscreen
    ; opening has to get it back here too. Without this, closing the app while pinned would leave a
    ; window the user cannot move or close by hand.
    try RestoreGameWindowFrame()
    return 0  ; anything non-zero would CANCEL the exit, which is never what this handler wants
}

; Starts the persistent OCR helper (ocr_server.exe) if it isn't already running, and waits for it
; to signal readiness. Returns true once a live, ready server exists; false if it couldn't be
; started (missing exe, launch error, or it never came up) - in which case callers fall back to
; the slower one-shot path. Cheap to call repeatedly: a no-op when the server is already up.
EnsureOcrServer() {
    global OcrServerPid, RuntimeDir, DataDir
    if (OcrServerPid && ProcessExist(OcrServerPid))
        return true

    OcrServerPid := 0
    exePath := RuntimeDir "\ocr_server.exe"
    if !FileExist(exePath)
        return false

    ; Clear any stale protocol files left by a previous (crashed) server before starting fresh.
    for f in ["ocr_ready.txt", "ocr_req.txt", "ocr_req.txt.tmp", "ocr_resp.txt", "ocr_resp.txt.tmp", "ocr_stop.txt"]
        try FileDelete DataDir "\" f

    pid := 0
    try {
        Run '"' exePath '" --dir "' DataDir '"', , "Hide", &pid
    } catch {
        return false
    }
    OcrServerPid := pid
    ; Immediately, before the readiness wait below: that wait can run for up to 15 seconds, and a
    ; helper is only covered by the kill-on-close backstop once it is actually in the job.
    AssignHelperToJob(pid)

    ; One-time startup wait (assembly load + engine creation). Generous timeout; only paid once.
    startWait := A_TickCount
    while (A_TickCount - startWait < 15000) {
        if FileExist(DataDir "\ocr_ready.txt")
            return true
        if !ProcessExist(OcrServerPid) {
            OcrServerPid := 0
            return false
        }
        Sleep 50
    }
    return true  ; assume slow-but-alive; the request path has its own timeout/fallback
}

; Starts the optional experimental OCR benchmark helper (ocr_benchmark.exe) if the user has
; unzipped one into RuntimeDir\ocr_benchmark - a no-op on every normal production install, which
; never has this folder. Unlike EnsureOcrServer this is called once at engine startup, not
; lazily per detection: the benchmark helper only watches a spool directory in the background, it
; has no per-request round trip the macro is waiting on.
EnsureOcrBenchmark() {
    global OcrBenchmarkPid, RuntimeDir, DataDir
    if (OcrBenchmarkPid && ProcessExist(OcrBenchmarkPid))
        return true

    OcrBenchmarkPid := 0
    exePath := RuntimeDir "\ocr_benchmark\ocr_benchmark.exe"
    if !FileExist(exePath)
        return false

    try FileDelete DataDir "\ocr_benchmark_stop.txt"

    pid := 0
    try {
        Run '"' exePath '" --dir "' DataDir '"', , "Hide", &pid
    } catch {
        return false
    }
    OcrBenchmarkPid := pid
    AssignHelperToJob(pid)
    return true
}

; Asks the OCR server to exit cleanly (and force-closes it if it doesn't), then clears protocol
; files. Called on app exit so no orphan ocr_server.exe process is left behind.
StopOcrServer() {
    global OcrServerPid, DataDir
    if !OcrServerPid
        return
    try FileAppend "1", DataDir "\ocr_stop.txt"
    ; Give it a brief moment to notice the stop file and exit on its own.
    waited := 0
    while (waited < 600 && ProcessExist(OcrServerPid)) {
        Sleep 50
        waited += 50
    }
    if ProcessExist(OcrServerPid) {
        ; ocr_server.exe is a PyInstaller onefile build: the tracked PID is a bootloader
        ; process that spawns its own child process to actually run the Python code, so a
        ; plain ProcessClose(OcrServerPid) here would only kill the bootloader and orphan
        ; the still-running child. taskkill's /T recursively kills that whole process tree.
        KillProcessTree(OcrServerPid)
        if ProcessExist(OcrServerPid)
            try ProcessClose(OcrServerPid)
    }
    OcrServerPid := 0
    for f in ["ocr_ready.txt", "ocr_req.txt", "ocr_req.txt.tmp", "ocr_resp.txt", "ocr_resp.txt.tmp", "ocr_stop.txt"]
        try FileDelete DataDir "\" f
}

; The same for the optional experimental benchmark helper, through its own stop file (STOP_FILENAME
; in ocr/ocr_helper/benchmark_runner.py). A no-op on every normal install, which never starts it.
StopOcrBenchmark() {
    global OcrBenchmarkPid, DataDir
    if !OcrBenchmarkPid
        return
    try FileAppend "1", DataDir "\ocr_benchmark_stop.txt"
    waited := 0
    while (waited < 600 && ProcessExist(OcrBenchmarkPid)) {
        Sleep 50
        waited += 50
    }
    if ProcessExist(OcrBenchmarkPid) {
        ; Same PyInstaller onefile shape as ocr_server.exe: the tracked PID is only the bootloader,
        ; so the kill has to take the whole tree or it orphans the child that does the actual work.
        KillProcessTree(OcrBenchmarkPid)
        if ProcessExist(OcrBenchmarkPid)
            try ProcessClose(OcrBenchmarkPid)
    }
    OcrBenchmarkPid := 0
    try FileDelete DataDir "\ocr_benchmark_stop.txt"
}

; Captures the given screen region and runs it through Windows' built-in OCR engine, returning the
; recognized text (may be empty). Uses the persistent OCR server (fast - assemblies already loaded)
; and falls back to a one-shot powershell.exe invocation only if the server can't be started or
; dies mid-request.
RunOcrOnRegion(x, y, w, h) {
    global OcrReqToken, OcrBusy, OcrServerPid, DataDir
    if (w <= 0 || h <= 0)
        return ""
    ; OcrBusy must bracket the ENTIRE operation - including EnsureOcrServer()'s own up-to-15s cold
    ; start and the one-shot fallback - not just the persistent-server request/response wait. This is
    ; the only thing that lets a second caller (e.g. the local IPC bridge's TEST_OCR verb) reliably
    ; detect "an OCR operation is already in progress" and avoid racing the shared request/response
    ; files; a caller checking this flag before an earlier version of this function set it could slip
    ; through during exactly that startup window.
    OcrBusy := true
    try {
        if !EnsureOcrServer()
            return RunOcrOneShot(x, y, w, h)

        token := ++OcrReqToken
        reqTmp := DataDir "\ocr_req.txt.tmp"
        reqFile := DataDir "\ocr_req.txt"
        respFile := DataDir "\ocr_resp.txt"

        try FileDelete respFile
        try FileDelete reqTmp
        try FileAppend token "|" x "|" y "|" w "|" h, reqTmp
        try FileMove reqTmp, reqFile, 1  ; atomic publish so the server never reads a half-written request

        text := ""
        startWait := A_TickCount
        while (A_TickCount - startWait < 6000) {
            if FileExist(respFile) {
                resp := ""
                try resp := FileRead(respFile)
                barPos := InStr(resp, "|")
                if (barPos && SubStr(resp, 1, barPos - 1) = token) {
                    text := Trim(SubStr(resp, barPos + 1), " `t`r`n")
                    try FileDelete respFile
                    break
                }
            }
            if !ProcessExist(OcrServerPid) {   ; server died mid-request - fall back for this scan
                OcrServerPid := 0
                return RunOcrOneShot(x, y, w, h)
            }
            Sleep 10
        }
        return text
    } finally {
        OcrBusy := false
    }
}

; Fallback path: one self-contained ocr_server.exe invocation in one-shot mode (--x/--y/--width/
; --height instead of just --dir). Slower (pays full engine startup each call) but has no
; dependency on a running server - used only when the persistent server is unavailable. The exe
; writes its own result file atomically, so no shell redirection is needed.
RunOcrOneShot(x, y, w, h) {
    global RuntimeDir, DataDir
    exePath := RuntimeDir "\ocr_server.exe"
    outFile := DataDir "\ocr_result.txt"
    try FileDelete outFile

    ; Unlike the old A_ComSpec/cmd.exe-wrapped launch (which always succeeded even if the
    ; wrapped script was missing), this launches ocr_server.exe directly, which throws if it
    ; cannot be found/started (missing, quarantined by AV, etc.) - must not go uncaught, or a
    ; single bad scan would take down the calling thread instead of just returning no text.
    try RunWait '"' exePath '" --dir "' DataDir '" --x ' x ' --y ' y ' --width ' w ' --height ' h, , "Hide"
    catch {
        return ""
    }

    text := ""
    try text := Trim(FileRead(outFile))
    return text
}

; Runs the step editor's own "Test OCR" button - tests whatever region/expected-text is currently
; entered for the selected Logic step (not necessarily saved yet).

; Returns true if any run of `minLen` consecutive characters from `needle` appears
; somewhere in `haystack` (case-insensitive). This is more forgiving than a full
; substring match, since OCR output can include extra lines (e.g. a difficulty
; label or category above/below the actual map name) or misread a stray character
; such as an apostrophe.
TextContainsPartialMatch(haystack, needle, minLen := 4) {
    haystackLower := StrLower(haystack)
    needleLower := StrLower(Trim(needle))
    len := StrLen(needleLower)
    if (len = 0)
        return false
    if (len <= minLen)
        return InStr(haystackLower, needleLower) > 0
    Loop len - minLen + 1 {
        chunk := SubStr(needleLower, A_Index, minLen)
        if InStr(haystackLower, chunk)
            return true
    }
    return false
}

; Scans `rect` via OCR and matches the result against each map profile's expected text. Checks
; every profile for an exact (full) match first, and only falls back to a forgiving 6-character
; partial match (for OCR misreads/extra lines) if nothing matched exactly - this ordering matters,
; since two map names that happen to share a short substring (e.g. "Kings Tomb" / "Rose Kingdom"
; both contain "king") could otherwise be confused with each other. Reads profile data directly
; from the ini file so it works regardless of what's shown in the UI.
DetectMapProfileInRegion(rect, timeoutSec := 5) {
    global MapProfileNames
    if (rect.w <= 0 || rect.h <= 0) {
        LogMsg("WARNING: this Detect Map step's region is not set.")
        return ""
    }

    ; Read each profile's expected text ONCE up front rather than re-hitting the ini file on every
    ; poll iteration (this loop can run ~16 times over a 5s timeout).
    profiles := []
    for name in MapProfileNames {
        expected := Cfg(GameMapProfileSection(name), "ExpectedText", "")
        if (expected != "")
            profiles.Push({Name: name, Expected: expected})
    }

    startTime := A_TickCount
    Loop {
        text := RunOcrOnRegion(rect.x, rect.y, rect.w, rect.h)
        if (text != "") {
            for p in profiles {
                if InStr(text, p.Expected)
                    return p.Name
            }
            for p in profiles {
                if TextContainsPartialMatch(text, p.Expected, 6)
                    return p.Name
            }
        }
        if (A_TickCount - startTime > timeoutSec * 1000)
            return ""
        Sleep 300
    }
}

; Runs the General tab's own "Test OCR" button - tests whatever region/expected-text is currently
; entered for Disconnect Detection (not necessarily saved yet).

; One OCR scan of `rect`, compared against `expected` using the same exact-then-fuzzy match as
; map detection. Returns false if the region or expected text isn't configured. `&recognizedText`
; (optional) receives whatever the OCR actually read, regardless of match result - callers that
; want to react to the raw text itself (e.g. TrackVictoryDefeat) can pass a variable for it.
IsTextDetectedInRegion(rect, expected, &recognizedText := "") {
    recognizedText := ""
    if (expected = "" || rect.w <= 0 || rect.h <= 0)
        return false
    text := RunOcrOnRegion(rect.x, rect.y, rect.w, rect.h)
    recognizedText := text
    if (text = "")
        return false
    return InStr(text, expected) || TextContainsPartialMatch(text, expected, 6)
}

; Reads a map profile's placement rows directly from the ini file (for use at runtime). A map with
; "custom tower slots" enabled also uses its own placement COUNT instead of the shared default.
GetMapProfilePlacements(name) {
    section := GameMapProfileSection(name)
    customTowers := Integer(Cfg(section, "CustomTowers", "0"))
    n := customTowers ? Integer(Cfg(section, "CustomNumPlacements", "4")) : Integer(Cfg(GameSection(), "NumPlacements", "4"))
    rows := []
    Loop n {
        i := A_Index
        slot := customTowers ? Cfg(section, "CustomSlot" i, "1") : Cfg(GameSection(), "Slot" i, "1")
        rows.Push({Slot: slot,
            X: Cfg(section, "Placement" i "X", "0"),
            Y: Cfg(section, "Placement" i "Y", "0")})
    }
    return rows
}

; Right-click-drags the camera from one point to another (e.g. to reset it to a fixed
; top-down angle) for maps that need it before towers are placed. Reads settings directly
; from ini so it works the same whether called from the running macro or tested manually.
; Shared right-click-drag primitive: moves to (startX,startY), holds right-click, drags in small
; interpolated steps to (endX,endY) over ~durMs, then releases. Used by both the per-map camera
; centering (Advanced Settings) and the standalone "Drag" step type.
DragRightClick(startX, startY, endX, endY, durMs) {
    global DryRun
    if DryRun
        return   ; Dry Run: skip the actual drag (the caller already logs what it would do)
    MouseMove startX, startY, 0
    Sleep 50
    Click startX, startY, "Right", 1, "D"
    Sleep 50
    steps := Max(5, Integer(durMs / 20))
    Loop steps {
        f := A_Index / steps
        ix := Round(startX + (endX - startX) * f)
        iy := Round(startY + (endY - startY) * f)
        MouseMove ix, iy, 0
        Sleep 20
    }
    Sleep 50
    Click endX, endY, "Right", 1, "U"
}

ZoomOutTicks(ticks) {
    if (ticks > 0) {
        ActWheelDown(ticks)
        LogMsg("  Zoomed out (" ticks " ticks).")
    }
}

; ============================================================
; PHYSICAL INPUT (honors Dry Run)
; ============================================================
; All actual clicking/typing/scrolling the running macro does goes through these, so "Dry Run"
; (test mode) can suppress the physical action in one place while everything else - logging, OCR,
; branching, waits - still runs exactly as normal.
; `desc`, when given, is logged as "Clicked <desc>." - deliberately WITHOUT the raw x/y coordinates,
; which are noise in the log. Callers that already log their own richer context leave it empty.
ActClick(x, y, desc := "") {
    global DryRun
    if !DryRun
        Click x, y
    if (desc != "")
        LogMsg("Clicked " desc ".")
}
ActSend(keys) {
    global DryRun
    if !DryRun
        Send keys
}
ActWheelDown(ticks) {
    global DryRun
    if !DryRun
        Click "WheelDown " ticks
}

; ============================================================
; MAP ADVANCED STEPS (Drag / Zoom Out actions, per map profile or shared [General])
; ============================================================

; Reads the ordered list of map actions for `section`. One-time migrates from the old single
; Center-Camera-drag + single Zoom-Out-ticks flags the first time a section is read, then persists
; the migrated list so this only happens once per section.
GetMapAdvSteps(section) {
    global ConfigFile
    if (Cfg(section, "AdvStepsMigrated", "0") != "1") {
        arr := []
        if (Integer(Cfg(section, "CenterCamera", "0"))) {
            arr.Push({Type: "Drag", X: Cfg(section, "CamStartX", "0"), Y: Cfg(section, "CamStartY", "0"),
                EndX: Cfg(section, "CamEndX", "0"), EndY: Cfg(section, "CamEndY", "0"), DragMs: Cfg(section, "CamDragMs", "500")})
        }
        if (Integer(Cfg(section, "ZoomOut", "0"))) {
            arr.Push({Type: "Zoom Out", X: Cfg(section, "ZoomTicks", "5"), Y: "0", EndX: "0", EndY: "0", DragMs: "500"})
        }
        SaveMapAdvStepsArr(section, arr)
        IniWrite 1, ConfigFile, section, "AdvStepsMigrated"
        return arr
    }
    n := Integer(Cfg(section, "AdvStepsCount", "0"))
    arr := []
    Loop n {
        i := A_Index
        arr.Push({Type: Cfg(section, "AdvStep" i "Type", "Drag"),
            X: Cfg(section, "AdvStep" i "X", "0"),
            Y: Cfg(section, "AdvStep" i "Y", "0"),
            EndX: Cfg(section, "AdvStep" i "EndX", "0"),
            EndY: Cfg(section, "AdvStep" i "EndY", "0"),
            DragMs: Cfg(section, "AdvStep" i "DragMs", "500")})
    }
    return arr
}

; Writes an array of {Type,X,Y,EndX,EndY,DragMs} objects to `section`.
SaveMapAdvStepsArr(section, arr) {
    global ConfigFile
    IniWrite arr.Length, ConfigFile, section, "AdvStepsCount"
    for i, s in arr {
        IniWrite s.Type, ConfigFile, section, "AdvStep" i "Type"
        IniWrite s.X, ConfigFile, section, "AdvStep" i "X"
        IniWrite s.Y, ConfigFile, section, "AdvStep" i "Y"
        IniWrite s.EndX, ConfigFile, section, "AdvStep" i "EndX"
        IniWrite s.EndY, ConfigFile, section, "AdvStep" i "EndY"
        IniWrite s.DragMs, ConfigFile, section, "AdvStep" i "DragMs"
    }
}

; ============================================================
; STEP EDITOR FIELD VISIBILITY (depends on step type)
; ============================================================
; "Logic" steps are the OCR-driven detection types - each has its own region + expected text and
; can jump to another screen on true/false. Everything else is a "Mechanic" step (an action).
IsLogicStepType(t) {
    return (t = "Detect Map" || t = "Round End Detection" || t = "Ingame Detection" || t = "Custom Detection")
}


; Runs only when the user manually picks a type from the dropdown - this always starts authoring a
; FRESH step of that type: every other field is cleared to its default (and any selected list row
; is deselected), so a new step never inherits the settings of the one that was last clicked. Named
; button steps get sensible default coordinates prefilled. Not called when loading an existing step
; (LoadEditorFromSelection calls UpdateStepEditorLabels directly), so editing never clobbers a step.

; Fires when the "Advanced Detection" checkbox itself is clicked. Seeds 2 default outcomes
; ("True"/"False", both "(continue)") the first time it's turned on for a step that doesn't have
; any yet - mirroring the normal True/False branch it replaces - so "Configure Outcomes..." (or
; committing the step right away) never starts from an empty, unusable list.

; ============================================================
; POSITION CAPTURE (F8) - with a red dot marker that follows the mouse
; ============================================================
GetMarkerSize() {
    size := SafeInt(Cfg(GameSection(), "MarkerSize", "4"), 4)
    return (size < 1) ? 1 : size
}

CreateMarker() {
    global MarkerGui
    MarkerGui := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x08000000")
    MarkerGui.BackColor := "FF0000"
    size := GetMarkerSize()
    MarkerGui.Show("x-100 y-100 w" size " h" size " NoActivate Hide")
}

UpdateMarkerPos() {
    global MarkerGui
    MouseGetPos &mx, &my
    size := GetMarkerSize()
    half := size // 2
    try MarkerGui.Move(mx - half, my - half, size, size)
}

HideMarker() {
    global MarkerGui
    try MarkerGui.Hide()
}


; The Python GUI has no live AHK edit control to receive a captured point, so it identifies the
; destination by field ID and consumes this one-shot result file instead.
BeginFieldCapture(fieldId) {
    global FieldCaptureId, MarkerGui, DataDir
    ; A previous capture's result must never satisfy a newly issued request.
    try FileDelete DataDir "\local_capture_result.txt"
    FieldCaptureId := fieldId
    try MarkerGui.Show("NoActivate")
    SetTimer UpdateMarkerPos, 30
    ToolTip "Move the mouse to the target position and press F8. Escape = Cancel."
}

WriteFieldCaptureResult(fieldId, cancelled := false, pctX := 0, pctY := 0) {
    global DataDir
    if cancelled
        json := '{"mode":"point","fieldId":' RemoteBridgeJsonStr(fieldId) ',"cancelled":true}'
    else
        json := '{"mode":"point","fieldId":' RemoteBridgeJsonStr(fieldId) ',"x":' pctX ',"y":' pctY '}'
    RemoteBridgeAtomicWrite(DataDir "\local_capture_result.txt", json)
}

F8:: {
    global MarkerGui, FieldCaptureId
    if (FieldCaptureId = "")
        return
    MouseGetPos &mx, &my
    pctX := PctXFromAbs(mx)
    pctY := PctYFromAbs(my)
    WriteFieldCaptureResult(FieldCaptureId, false, pctX, pctY)
    FieldCaptureId := ""
    SetTimer UpdateMarkerPos, 0
    size := GetMarkerSize()
    half := size // 2
    try MarkerGui.Move(mx - half, my - half, size, size)
    SetTimer HideMarker, -2000
    ToolTip()
}

; ============================================================
; OCR REGION CAPTURE (snipping-tool style: drag a red rectangle)
; ============================================================
; Instead of setting the two opposite corners of an OCR region with two separate F8 point captures,
; this lets you drag a single rectangle (like the Windows Snipping Tool): the app windows hide, the
; screen dims, and a red rectangle follows the mouse while the left button is held. On release, the
; rectangle's corners are written (as window-relative percentages) to its GUI controls or Python field IDs.

; Field-ID capture deliberately shares the legacy overlay construction and drag tracker, so Python and
; native GUI callers see the same selection behavior instead of maintaining two visual capture paths.
BeginRegionCapture(fieldId1, fieldId2, fieldId3, fieldId4) {
    global RegionCapActive, RegionCapTargets, RegionCapFieldIds, DataDir
    if RegionCapActive
        return
    ; Discard a completed prior request before beginning a capture that will publish a new result.
    try FileDelete DataDir "\local_capture_result.txt"
    RegionCapFieldIds := [fieldId1, fieldId2, fieldId3, fieldId4]
    RegionCapTargets := ""
    SetupRegionCapture()
}

SetupRegionCapture() {
    global RegionCapActive, RegionCapPhase, RegionCapTargets
    global RegionDimGui, RegionBandGuis

    ; A dim, click-catching overlay across every monitor (so a click lands here, never on the game).
    vx := DllCall("GetSystemMetrics", "Int", 76, "Int")
    vy := DllCall("GetSystemMetrics", "Int", 77, "Int")
    vw := DllCall("GetSystemMetrics", "Int", 78, "Int")
    vh := DllCall("GetSystemMetrics", "Int", 79, "Int")
    RegionDimGui := Gui("+AlwaysOnTop -Caption +ToolWindow")
    RegionDimGui.BackColor := "202020"
    RegionDimGui.Show("x" vx " y" vy " w" vw " h" vh " NoActivate")
    try WinSetTransparent 90, RegionDimGui.Hwnd

    ; 4 thin red bars forming the live rubber-band outline (created once, moved while dragging).
    RegionBandGuis := []
    Loop 4 {
        b := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x08000000")
        b.BackColor := "FF2A2A"
        b.Show("x-10 y-10 w1 h1 NoActivate Hide")
        RegionBandGuis.Push(b)
    }

    RegionCapPhase := 0
    RegionCapActive := true
    ToolTip "Click and drag a rectangle over the OCR region. Release to set it. Esc = cancel."
    SetTimer RegionCaptureTick, 15
}

RegionCaptureTick() {
    global RegionCapActive, RegionCapPhase, RegionCapStartX, RegionCapStartY
    if !RegionCapActive
        return
    MouseGetPos &mx, &my
    pressed := GetKeyState("LButton", "P")
    if (RegionCapPhase = 0) {
        if pressed {
            RegionCapStartX := mx
            RegionCapStartY := my
            RegionCapPhase := 1
            UpdateRegionBand(mx, my, mx, my)
        }
        return
    }
    if pressed
        UpdateRegionBand(RegionCapStartX, RegionCapStartY, mx, my)
    else
        FinishRegionCapture(RegionCapStartX, RegionCapStartY, mx, my)
}

UpdateRegionBand(x1, y1, x2, y2) {
    global RegionBandGuis
    if (RegionBandGuis.Length < 4)
        return
    left := Min(x1, x2), top := Min(y1, y2)
    right := Max(x1, x2), bottom := Max(y1, y2)
    w := right - left, h := bottom - top
    t := 2
    bars := [{x: left, y: top, w: w + t, h: t},          ; top
             {x: left, y: bottom, w: w + t, h: t},        ; bottom
             {x: left, y: top, w: t, h: h + t},           ; left
             {x: right, y: top, w: t, h: h + t}]          ; right
    for i, b in bars
        try RegionBandGuis[i].Show("x" b.x " y" b.y " w" Max(1, b.w) " h" Max(1, b.h) " NoActivate")
}

WriteRegionCaptureResult(cancelled := false, left := 0, top := 0, right := 0, bottom := 0) {
    global RegionCapFieldIds, DataDir
    fieldIdsJson := "[" RemoteBridgeJsonStr(RegionCapFieldIds[1]) "," RemoteBridgeJsonStr(RegionCapFieldIds[2]) "," RemoteBridgeJsonStr(RegionCapFieldIds[3]) "," RemoteBridgeJsonStr(RegionCapFieldIds[4]) "]"
    if cancelled
        json := '{"mode":"region","fieldIds":' fieldIdsJson ',"cancelled":true}'
    else
        json := '{"mode":"region","fieldIds":' fieldIdsJson ',"x1":' PctXFromAbs(left) ',"y1":' PctYFromAbs(top) ',"x2":' PctXFromAbs(right) ',"y2":' PctYFromAbs(bottom) '}'
    RemoteBridgeAtomicWrite(DataDir "\local_capture_result.txt", json)
}

FinishRegionCapture(sx, sy, ex, ey) {
    global RegionCapTargets
    global RegionCapFieldIds
    left := Min(sx, ex), top := Min(sy, ey)
    right := Max(sx, ex), bottom := Max(sy, ey)
    CleanupRegionCapture()
    if (right - left < 3 || bottom - top < 3) {
        if (RegionCapFieldIds.Length > 0) {
            WriteRegionCaptureResult(true)
            RegionCapFieldIds := []
            return
        }
        LogMsg("Region capture cancelled (selection too small).")
        return
    }
    if (RegionCapFieldIds.Length > 0) {
        WriteRegionCaptureResult(false, left, top, right, bottom)
        RegionCapFieldIds := []
        LogMsg("OCR region set.")
        return
    }
    RegionCapTargets[1].Value := PctXFromAbs(left)
    RegionCapTargets[2].Value := PctYFromAbs(top)
    RegionCapTargets[3].Value := PctXFromAbs(right)
    RegionCapTargets[4].Value := PctYFromAbs(bottom)
    LogMsg("OCR region set.")
}

CancelRegionCapture() {
    global RegionCapFieldIds
    if (RegionCapFieldIds.Length > 0) {
        WriteRegionCaptureResult(true)
        RegionCapFieldIds := []
    }
    CleanupRegionCapture()
    LogMsg("Region capture cancelled.")
}

CleanupRegionCapture() {
    global RegionCapActive, RegionCapPhase, RegionDimGui, RegionBandGuis, RegionCapRestore
    SetTimer RegionCaptureTick, 0
    ToolTip()
    RegionCapActive := false
    RegionCapPhase := 0
    if (RegionDimGui != "") {
        try RegionDimGui.Destroy()
        RegionDimGui := ""
    }
    for g in RegionBandGuis
        try g.Destroy()
    RegionBandGuis := []
    ; Re-show the hidden windows in the order they were hidden (main window first), preserving z-order.
    for g in RegionCapRestore
        try g.Show()
    RegionCapRestore := []
}

; Fires from the step editor's Set Position/Select Region button. Logic (detection) steps select a
; whole OCR region by dragging a rectangle; every other step type captures a single point via F8.

; ============================================================
; GAME WINDOW / PROCESS LIST
; ============================================================

EnumerateGameProcessCandidates() {
    candidates := []
    seen := Map()
    ownPID := ProcessExist()
    for hwnd in WinGetList() {
        try {
            pid := WinGetPID(hwnd)
            if (pid = ownPID)
                continue
            title := WinGetTitle(hwnd)
            if (title = "")
                continue
            proc := WinGetProcessName(hwnd)
            if (proc = "" || seen.Has(proc))
                continue
            seen[proc] := true
            candidates.Push({Title: title, Proc: proc})
        }
    }
    return candidates
}

; Reads the native "title | process" dropdown control - used only by BuildGeneralSaveData() (the
; still-live native GUI's own Save-button snapshotter) so a freshly picked entry actually persists.
; The engine itself must NOT use this: see ConfiguredGameProcess() below.

; The persisted process name the engine should actually act on (config.ini, kept current by
; whichever explicit Save action - the native GUI, or the Python GUI writing config.ini itself -
; last ran).
; Deliberately separate from GetSelectedGameProcess(): that one reads a native GUI control the
; engine must not depend on, since a later phase deletes it.
ConfiguredGameProcess() {
    return Cfg("General", "GameProcess", "")
}

DetectBackgroundWindowsSession() {
    ; The overlay only helps on the desktop the user is actually looking at. A session that is
    ; not the physical console is the background RDP session the app itself starts.
    try {
        sessionId := 0
        if !DllCall("kernel32\ProcessIdToSessionId", "UInt", DllCall("kernel32\GetCurrentProcessId", "UInt"), "UInt*", &sessionId, "Int")
            return false
        consoleSessionId := DllCall("kernel32\WTSGetActiveConsoleSessionId", "UInt")
        if (consoleSessionId = 0xFFFFFFFF)
            return false
        return sessionId != consoleSessionId
    } catch Any {
        ; "catch Any" rather than a bare "catch": the latter only catches Error, so a non-Error
        ; throw would escape and take the whole startup with it, over a purely cosmetic decision.
        return false
    }
}

; ============================================================
; FULLSCREEN GRAY OVERLAY WITH A RECTANGULAR OPENING
; Built from 4 borderless always-on-top bars forming a frame around the opening,
; instead of punching an actual hole in one window (simpler and more reliable).
; ============================================================
; The single place the opening is read from, so switching it to the whole screen here is enough for
; everything downstream to follow: the percent<->pixel conversions, the window pin and its lock, and
; the gray overlay (whose four bars all come out zero-sized and simply draw nothing).
;
; A_ScreenWidth/Height is the PRIMARY monitor of the Windows session this engine runs in, which is
; also the right answer inside a background RDP session: that session has its own screen, and the
; engine running there reads its size rather than the physical desktop's.
GetHoleRect() {
    if FullscreenOpeningEnabled()
        return {x: 0, y: 0, w: A_ScreenWidth, h: A_ScreenHeight}
    return {x: SafeInt(Cfg("General", "HoleX", 0)), y: SafeInt(Cfg("General", "HoleY", 0)),
        w: SafeInt(Cfg("General", "HoleW", 0)), h: SafeInt(Cfg("General", "HoleH", 0))}
}

; Reads the same spellings the Python side's _boolean() accepts (gui/ipc/config_reader.py), not just
; "1". Both sides answer this question about the same key, and the GUI decides from its answer
; whether the stored opening values still mean anything; a config the two read differently would
; grey those values out in the window while the engine went on using them.
FullscreenOpeningEnabled() {
    value := StrLower(Trim(Cfg("General", "FullscreenOpening", "0")))
    return (value = "1" || value = "true" || value = "yes" || value = "on")
}

; Whether this engine must leave the game window's size and position entirely to the game.
;
; The single place that question is answered, so "the engine never touches the geometry in a
; background session" is one condition rather than a rule spread over every caller that happens to
; move a window.
;
; BOTH halves are load-bearing. A background session exists only to run the game, so putting the
; window where it belongs after the fact is work with no purpose there and is visible as a resize
; the moment somebody connects to look. But every click the macro sends is a percentage OF THE
; OPENING (see AbsXY), so the engine may only stop asserting the window's rectangle once the
; rectangle the game produces by itself already IS that opening. With FullscreenOpening on it is:
; the opening is the session's whole screen (GetHoleRect above), and the session starts Roblox with
; Roblox' own fullscreen setting on (gui/app/roblox_display.py), so the window covers that same
; screen from the moment it appears. With the option off the opening is a smaller rectangle nothing
; else would ever move the window into, and skipping the move would leave every stored coordinate
; pointing somewhere the game is not.
;
; Nothing watches the window afterwards, and nothing needs to: the engine's own lock was the only
; thing in a background session that ever moved a window, and there is no user in front of that
; desktop to drag or resize one.
;
; This is the POLICY only, which is why it is not the thing anything else reads: whether the geometry
; was really left alone is GameWindowGeometryWasLeftToGame() below, because policy alone can be true
; while the game came up windowed anyway.
LeaveGameWindowGeometryAlone() {
    global InBackgroundWindowsSession
    return InBackgroundWindowsSession && FullscreenOpeningEnabled()
}

; Whether the window's VISIBLE rectangle already IS the opening, within a couple of pixels.
;
; The check that turns the policy above into a decision, and it exists because the two halves of this
; feature live in different processes. The session asks Roblox to start full screen by writing its
; own setting (gui/app/roblox_display.py), and that can fail for reasons the engine never hears
; about: a settings file that is missing, locked, or written in a shape that module refuses to edit.
; Trusting the config alone would then leave the macro clicking full screen coordinates at a
; windowed client, which is silently wrong in every step. Measuring the window instead means the
; worst case is the old behaviour (position it) rather than a broken run.
;
; Uses the same visible-edge measurement the positioning does, so a window with an invisible resize
; border is compared on the edges the user (and the opening) actually see. Any failure answers "no",
; which falls back to positioning: the safe direction.
;
; Deliberately measured at each ForceGameWindow and not watched afterwards. Re-checking on a timer is
; what the lock already was, and putting one back is exactly the work this task removed; the window
; would have to change shape with nobody in front of that desktop to change it. The per-start
; measurement is what the engine can honestly verify, and every restart the engine already performs
; (a new run, a disconnect reconnect, a preset switch) takes it again.
GameWindowFillsOpening(hwnd) {
    hole := GetHoleRect()
    if (hole.w <= 0 || hole.h <= 0)
        return false
    try {
        WinGetPos &wx, &wy, &ww, &wh, "ahk_id " hwnd
        GetVisibleFrameGaps(hwnd, &lg, &tg, &rg, &bg)
        tolerance := 2   ; absorbs rounding in the DWM frame measurement, nothing more
        return Abs((wx + lg) - hole.x) <= tolerance &&
            Abs((wy + tg) - hole.y) <= tolerance &&
            Abs((ww - lg - rg) - hole.w) <= tolerance &&
            Abs((wh - tg - bg) - hole.h) <= tolerance
    }
    return false
}

; What the most recent ForceGameWindow attempt actually did, so the messages Pin and the local
; bridge's FORCE_GAME_WINDOW verb report describe that attempt rather than the config that allowed
; it. Reporting only: the running lock is not driven from here, see EnforceWindowLock.
GameWindowGeometryWasLeftToGame() {
    global GameWindowLeftToGame
    return GameWindowLeftToGame
}

CreateOverlay() {
    global OverlayGuis, OverlayVisible, InBackgroundWindowsSession, LogGui, LogEdit, LogLines, StatsGui
    global StatsMapText, StatsScreenText, StatsStepText
    global StatsStepRepeatText, StatsStartRepeatText, StatsVictoryText, StatsDefeatText
    global StatsSessionTimeText, StatsCurrentStepTimeText, StatsLastVals
    global TimeBreakdownGui, ScreenTimeLV
    if OverlayVisible
        return
    if InBackgroundWindowsSession {
        LogMsg("Background Windows session: on-screen overlay skipped.")
        return
    }
    hole := GetHoleRect()
    screenW := A_ScreenWidth
    screenH := A_ScreenHeight

    bars := [
        {x: 0, y: 0, w: screenW, h: hole.y},                                          ; top
        {x: 0, y: hole.y + hole.h, w: screenW, h: screenH - (hole.y + hole.h)},        ; bottom
        {x: 0, y: hole.y, w: hole.x, h: hole.h},                                       ; left
        {x: hole.x + hole.w, y: hole.y, w: screenW - (hole.x + hole.w), h: hole.h}     ; right
    ]

    for b in bars {
        if (b.w <= 0 || b.h <= 0)
            continue
        g := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x08000000")
        g.BackColor := "3C3C3C"
        g.Show("x" b.x " y" b.y " w" b.w " h" b.h " NoActivate")
        OverlayGuis.Push(g)
    }

    ; Log panel + Time Breakdown panel: together fill a column to the right of the game window,
    ; from the top of the opening down to bottomMargin px above the screen's bottom edge - i.e. as
    ; tall as the Stats bar below is, not just as tall as the game window/opening itself. Inset
    ; panelGap from the hole's right edge (the same gap used below the game window before the Stats
    ; panel, so the two match visually) and rightMargin from the screen's own right edge (matching
    ; the gray margin already visible on the left, hole.x).
    panelGap := 20
    rightMargin := 50
    bottomMargin := 50
    rightW := screenW - (hole.x + hole.w)
    panelX := hole.x + hole.w + panelGap
    panelW := rightW - panelGap - rightMargin
    columnH := screenH - hole.y - bottomMargin
    if (rightW > panelGap + rightMargin + 80 && panelW > 80 && columnH > 150) {
        margin := 10
        breakdownH := 320
        breakdownGap := 10
        showBreakdown := (columnH - breakdownH - breakdownGap) >= 150
        logH := showBreakdown ? (columnH - breakdownH - breakdownGap) : columnH

        LogGui := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x08000000")
        LogGui.BackColor := "000000"
        LogGui.SetFont("s9 cWhite", "Consolas")
        LogEdit := LogGui.AddEdit("x" margin " y" margin " w" (panelW - margin * 2) " h" (logH - margin * 2)
            . " ReadOnly VScroll Background000000 cWhite")
        LogGui.Show("x" panelX " y" hole.y " w" panelW " h" logH " NoActivate")
        ; Seed the panel with whatever's already in the log so far, instead of starting blank.
        RenderLogPanel()

        if showBreakdown {
            innerW := panelW - margin * 2
            innerH := breakdownH - margin * 2
            headerH := 18

            TimeBreakdownGui := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x08000000")
            TimeBreakdownGui.BackColor := "000000"

            TimeBreakdownGui.SetFont("s9 cWhite Bold", "Segoe UI")
            TimeBreakdownGui.AddText("x" margin " y" margin " w" innerW " h" headerH, "Screen Time")
            TimeBreakdownGui.SetFont("s9 cWhite Norm", "Consolas")
            ScreenTimeLV := TimeBreakdownGui.AddListView(
                "x" margin " y" (margin + headerH) " w" innerW " h" (innerH - headerH) " NoSortHdr -Multi",
                ["Screen", "Time"])
            ScreenTimeLV.ModifyCol(1, Integer(innerW * 0.65))
            ScreenTimeLV.ModifyCol(2, Integer(innerW * 0.35) - 20)
            StyleOverlayListView(ScreenTimeLV)

            TimeBreakdownGui.Show("x" panelX " y" (hole.y + logH + breakdownGap) " w" panelW " h" breakdownH " NoActivate")
            RenderTimeBreakdownPanel()
        } else {
            TimeBreakdownGui := ""
            ScreenTimeLV := ""
        }
    } else {
        LogGui := ""
        LogEdit := ""
        TimeBreakdownGui := ""
        ScreenTimeLV := ""
    }

    ; Application Stats panel: a black bar BELOW the game window, spanning just its width (the
    ; Log/Time Breakdown column to the right now runs down alongside it instead of sharing this
    ; row), placed in the bottom gray bar.
    statsAreaY := hole.y + hole.h
    statsAreaH := screenH - statsAreaY
    if (statsAreaH > 190) {
        statsMargin := 10
        statsGapTop := panelGap      ; same gap as the log/time-breakdown column's top-side inset
        statsGapBottom := bottomMargin   ; same bottom margin the log/time-breakdown column ends at
        statsX := hole.x
        statsW := hole.w
        statsH := Max(190, statsAreaH - statsGapTop - statsGapBottom)
        statsY := statsAreaY + statsGapTop

        StatsGui := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x08000000")
        StatsGui.BackColor := "000000"

        StatsGui.SetFont("s13 cWhite Bold", "Segoe UI")
        StatsGui.AddText("x" statsMargin " y" statsMargin " w" (statsW - statsMargin * 2 - 80) " h26", "Application Stats")
        StatsGui.SetFont("s9 cBlack Norm", "Segoe UI")
        statsCopyBtn := StatsGui.AddButton("x" (statsW - statsMargin - 70) " y" statsMargin " w70 h22", "Copy")
        statsCopyBtn.OnEvent("Click", (*) => CopyStatsClick())

        ; All 3 rows have 3 evenly spaced columns - label on top, big value underneath. Row 1 is
        ; this run's live location; Row 2 mixes this-run counters with Session Time and Current Step
        ; Time; Row 3 is the lifetime counters (Start Repeat/Victory/Defeat survive an internal
        ; restart, unlike everything else here).
        colW := Integer((statsW - statsMargin * 2) / 3)
        row1Labels := ["Current Map", "Current Screen", "Current Step"]
        row2Labels := ["Session Time", "Step Repetition Count", "Current Step Time"]
        row3Labels := ["Start Repetition Count", "Victory Count", "Defeat Count"]
        rowY1 := statsMargin + 44
        rowY2 := rowY1 + 54
        rowY3 := rowY2 + 54
        row1Texts := []
        row2Texts := []
        row3Texts := []
        loop 3 {
            colX := statsMargin + (A_Index - 1) * colW
            StatsGui.SetFont("s9 cWhite Norm", "Segoe UI")
            StatsGui.AddText("x" colX " y" rowY1 " w" (colW - 10) " h16", row1Labels[A_Index])
            StatsGui.SetFont("s14 cWhite Bold", "Segoe UI")
            row1Texts.Push(StatsGui.AddText("x" colX " y" (rowY1 + 20) " w" (colW - 10) " h26", "-"))

            StatsGui.SetFont("s9 cWhite Norm", "Segoe UI")
            StatsGui.AddText("x" colX " y" rowY2 " w" (colW - 10) " h16", row2Labels[A_Index])
            StatsGui.SetFont("s14 cWhite Bold", "Segoe UI")
            row2Texts.Push(StatsGui.AddText("x" colX " y" (rowY2 + 20) " w" (colW - 10) " h26", "-"))

            StatsGui.SetFont("s9 cWhite Norm", "Segoe UI")
            StatsGui.AddText("x" colX " y" rowY3 " w" (colW - 10) " h16", row3Labels[A_Index])
            StatsGui.SetFont("s14 cWhite Bold", "Segoe UI")
            row3Texts.Push(StatsGui.AddText("x" colX " y" (rowY3 + 20) " w" (colW - 10) " h26", "-"))
        }
        StatsMapText := row1Texts[1]
        StatsScreenText := row1Texts[2]
        StatsStepText := row1Texts[3]
        StatsSessionTimeText := row2Texts[1]
        StatsStepRepeatText := row2Texts[2]
        StatsCurrentStepTimeText := row2Texts[3]
        StatsStartRepeatText := row3Texts[1]
        StatsVictoryText := row3Texts[2]
        StatsDefeatText := row3Texts[3]
        StatsLastVals := Map()   ; fresh controls (all showing "-") - clear the change-cache so the

        StatsGui.Show("x" statsX " y" statsY " w" statsW " h" statsH " NoActivate")
        RenderStatsPanel()       ; ...first render populates every row
    } else {
        StatsGui := ""
        StatsMapText := ""
        StatsScreenText := ""
        StatsStepText := ""
        StatsStepRepeatText := ""
        StatsStartRepeatText := ""
        StatsVictoryText := ""
        StatsDefeatText := ""
        StatsSessionTimeText := ""
        StatsCurrentStepTimeText := ""
    }

    OverlayVisible := true
    ; Session Time and Current Step Time tick up live even while nothing else changes (e.g. mid-wait
    ; on a single long-running step) - a 1s timer is enough to keep both readable without the
    ; WM_SETTEXT/repaint churn a faster interval would add.
    SetTimer StatsTick, 1000
    LogMsg("Overlay opened.")
}

; Ticks the live time displays (Session Time and Current Step Time in Application Stats) once a
; second while the overlay is open - both render functions are safe to call even when their panel
; doesn't exist.
StatsTick() {
    RenderStatsPanel()
    RenderTimeBreakdownPanel()
}

CloseOverlay(*) {
    global OverlayGuis, OverlayVisible, LockedProcess, GameWindowLeftToGame, LogGui, LogEdit, StatsGui
    global StatsMapText, StatsScreenText, StatsStepText
    global StatsStepRepeatText, StatsStartRepeatText, StatsVictoryText, StatsDefeatText
    global StatsSessionTimeText, StatsCurrentStepTimeText
    global TimeBreakdownGui, ScreenTimeLV
    hadOverlay := OverlayVisible
    SetTimer EnforceWindowLock, 0
    SetTimer StatsTick, 0
    LockedProcess := ""
    ; Released with the lock it belongs to. The decision describes one run's window, so letting a
    ; stale "left to the game" outlive that run would word the next Pin's message from a window
    ; nobody has looked at yet, and would silence a lock timer started outside ForceGameWindow.
    GameWindowLeftToGame := false
    ; The game keeps running after the macro stops, so it must not be left without its title bar:
    ; there would be no way to move or close it by hand.
    RestoreGameWindowFrame()
    for g in OverlayGuis {
        try g.Destroy()
    }
    OverlayGuis := []
    if (LogGui != "") {
        try LogGui.Destroy()
    }
    LogGui := ""
    LogEdit := ""
    if (TimeBreakdownGui != "") {
        try TimeBreakdownGui.Destroy()
    }
    TimeBreakdownGui := ""
    ScreenTimeLV := ""
    if (StatsGui != "") {
        try StatsGui.Destroy()
    }
    StatsGui := ""
    StatsMapText := ""
    StatsScreenText := ""
    StatsStepText := ""
    StatsStepRepeatText := ""
    StatsStartRepeatText := ""
    StatsVictoryText := ""
    StatsDefeatText := ""
    StatsSessionTimeText := ""
    StatsCurrentStepTimeText := ""
    OverlayVisible := false
    LogMsg(hadOverlay ? "Overlay closed. Window lock released." : "Window lock released.")
}

; Title bar and resize frame, stripped while the opening IS the whole screen so the game's own
; picture fills it instead of stopping below a caption. Kept to that one case on purpose: with a
; smaller opening the frame is what the user grabs to see and move the window, and taking it away
; there would change long-standing behavior for no gain.
;
; The original style is remembered ON DISK, not in a variable, and that is the whole point: the game
; outlives this process. A crash or a taskkill between stripping the frame and putting it back would
; otherwise leave a window with no title bar and nothing left anywhere that knows what it used to
; have, since a later engine cannot tell "we took its frame away" from "it never had one". The
; marker turns that into a recoverable state: whoever runs next finds it and can undo the change.
;
; It records the process name alongside the handle because Windows reuses window handles. Restoring
; is refused when the handle now belongs to something else, so a recycled handle costs a missed
; restore rather than a caption bolted onto an unrelated window.
;
; The style bits live inside the function rather than in a script-level constant on purpose: this
; script's auto-execute section ends at its first hotkey (F8, far above here), so a top-level
; assignment down here would never run and the "constant" would read as empty.
GameFrameMarkerPath() {
    global DataDir
    return DataDir "\game_frame_restore.txt"
}

; Returns whether the way back is now actually on disk. The caller must not strip the frame when
; this says no: a window with no title bar and no record of what it had is exactly the state this
; marker exists to prevent, and an unwritable data directory is not a reason to create it.
;
; FileOpen("w") rather than delete-then-append: a delete that quietly failed would leave FileAppend
; adding to the OLD record, and the frame would then be stripped against a marker describing a
; different window. "w" truncates as part of opening, so there is no in-between state to get wrong.
; UTF-8-RAW because this is read back byte for byte and a BOM would corrupt the first field.
WriteGameFrameMarker(hwnd, style, processName) {
    try {
        handle := FileOpen(GameFrameMarkerPath(), "w", "UTF-8-RAW")
        if !IsObject(handle)
            return false
        handle.Write(hwnd "|" style "|" processName)
        handle.Close()
    } catch Any {
        return false
    }
    return true
}

; A marker that cannot be read or does not parse is DELETED rather than left in place. It can never
; restore anything, so keeping it would only make every later call read it again and fail again.
ReadGameFrameMarker() {
    path := GameFrameMarkerPath()
    if !FileExist(path)
        return ""
    text := ""
    try text := Trim(FileRead(path, "UTF-8"))
    parts := StrSplit(text, "|")
    if (parts.Length >= 2) {
        hwnd := SafeInt(parts[1]), style := SafeInt(parts[2])
        if (hwnd != 0 && style != 0)
            return {hwnd: hwnd, style: style, proc: parts.Length >= 3 ? parts[3] : ""}
    }
    try FileDelete(path)
    return ""
}

; Safe to call as often as the window lock's timer does (twice a second). Two statics keep the
; steady state free of file access and of a repeated warning: once a window is settled, or once it
; has been warned about, the same window in the same mode costs nothing at all.
ApplyBorderlessGameWindow(hwnd) {
    static settledHwnd := 0, warned := false
    GAME_FRAME_STYLE_BITS := 0x00C40000   ; WS_CAPTION | WS_THICKFRAME
    if !FullscreenOpeningEnabled() {
        if (settledHwnd = hwnd)
            return
        if RestoreGameWindowFrame()
            settledHwnd := hwnd
        return
    }
    settledHwnd := 0   ; the option is on again, so this window is no longer settled as framed
    try {
        style := WinGetStyle("ahk_id " hwnd)
        ; Already borderless, so there is nothing to strip and nothing new to remember. Returning
        ; here is also what keeps this safe to call repeatedly (the window lock does, every tick):
        ; overwriting the marker now would record the STRIPPED style as the one to restore.
        if !(style & GAME_FRAME_STYLE_BITS)
            return
        processName := ""
        try processName := WinGetProcessName("ahk_id " hwnd)
        ; Written BEFORE the change, so a crash in between still leaves the way back on disk, and
        ; the change is abandoned when it could not be written at all.
        if !WriteGameFrameMarker(hwnd, style, processName) {
            ; A latch, not a per-window one: the lock re-runs this twice a second, and the reason a
            ; write fails is the data directory rather than the window, so two windows taking turns
            ; would otherwise clear each other's flag and log on every tick. Reset by the first
            ; write that succeeds, so a directory that becomes writable again can report the next
            ; failure.
            if !warned {
                warned := true
                LogMsg("WARNING: could not record how to restore the game window's title bar, so it was left in place.")
            }
            return
        }
        warned := false
        WinSetStyle("-" GAME_FRAME_STYLE_BITS, "ahk_id " hwnd)
        NotifyFrameChanged(hwnd)
    }
}

; Returns whether there is nothing left to put back, which is what lets the caller stop asking. Note
; that a successful restore whose marker file could not be deleted still counts as done: the window
; already has its frame, and re-applying the same style to it later is a no-op. The one case that
; answers "not done" is a restore that actually failed, because there the way back still matters.
RestoreGameWindowFrame() {
    marker := ReadGameFrameMarker()
    if (marker = "")
        return true
    try {
        if !WinExist("ahk_id " marker.hwnd) {
            try FileDelete(GameFrameMarkerPath())
            return true
        }
        if (marker.proc != "" && WinGetProcessName("ahk_id " marker.hwnd) != marker.proc) {
            ; Windows handed this handle to another window; leave that window alone. Matching on
            ; the executable name is deliberately all this checks: a recycled handle held by a
            ; SECOND window of the same game would pass, and putting a title bar back on that one
            ; is harmless, while a stricter identity check would cost a restore whenever the game
            ; legitimately restarted.
            try FileDelete(GameFrameMarkerPath())
            return true
        }
        WinSetStyle(marker.style, "ahk_id " marker.hwnd)
        NotifyFrameChanged(marker.hwnd)
        try FileDelete(GameFrameMarkerPath())
        return true
    }
    return false
}

; A style change alone does not make Windows recompute the non-client area, so the title bar can
; stay drawn (or stay missing) until something else happens to the window. This is the documented
; way to ask for that recalculation without moving, resizing or activating anything.
NotifyFrameChanged(hwnd) {
    SWP_NOSIZE := 0x0001, SWP_NOMOVE := 0x0002, SWP_NOZORDER := 0x0004
    SWP_NOACTIVATE := 0x0010, SWP_FRAMECHANGED := 0x0020
    flags := SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
    try DllCall("SetWindowPos", "Ptr", hwnd, "Ptr", 0, "Int", 0, "Int", 0, "Int", 0, "Int", 0, "UInt", flags)
}

; Removes the Windows 11 rounded-corner effect on a window so it fills the
; opening flush, with no background peeking through at the corners.
DisableRoundedCorners(hwnd) {
    DWMWA_WINDOW_CORNER_PREFERENCE := 33
    DWMWCP_DONOTROUND := 1
    pref := DWMWCP_DONOTROUND
    try DllCall("dwmapi\DwmSetWindowAttribute", "Ptr", hwnd, "UInt", DWMWA_WINDOW_CORNER_PREFERENCE, "Int*", pref, "Int", 4)
}

; Windows reserves an invisible resize border around most windows that is not part of
; the rect WinMove positions, but does shift the visible edge inward by a few pixels.
; This measures that gap via DWM's "extended frame bounds" so we can compensate for it.
GetVisibleFrameGaps(hwnd, &leftGap, &topGap, &rightGap, &bottomGap) {
    WinGetPos &wx, &wy, &ww, &wh, "ahk_id " hwnd
    rect := Buffer(16, 0)
    result := DllCall("dwmapi\DwmGetWindowAttribute", "Ptr", hwnd, "UInt", 9, "Ptr", rect, "UInt", 16)
    if (result != 0) {
        leftGap := 0, topGap := 0, rightGap := 0, bottomGap := 0
        return
    }
    fl := NumGet(rect, 0, "Int")
    ft := NumGet(rect, 4, "Int")
    fr := NumGet(rect, 8, "Int")
    fb := NumGet(rect, 12, "Int")
    leftGap := fl - wx
    topGap := ft - wy
    rightGap := (wx + ww) - fr
    bottomGap := (wy + wh) - fb
}

; Moves a window so its VISIBLE edges land exactly on the target rect, correcting for
; the invisible border gap measured above.
MoveWindowToVisibleRect(hwnd, targetX, targetY, targetW, targetH) {
    WinMove targetX, targetY, targetW, targetH, "ahk_id " hwnd
    Sleep 50
    GetVisibleFrameGaps(hwnd, &lg, &tg, &rg, &bg)
    correctedX := targetX - lg
    correctedY := targetY - tg
    correctedW := targetW + lg + rg
    correctedH := targetH + tg + bg
    WinMove correctedX, correctedY, correctedW, correctedH, "ahk_id " hwnd
}

; Continuously snaps the game window back into the opening if it gets dragged or resized.
EnforceWindowLock() {
    global LockedProcess
    if (LockedProcess = "")
        return
    ; Deliberately NOT guarded on GameWindowGeometryWasLeftToGame() here. That flag records the most
    ; recent ForceGameWindow attempt, and Pin is such an attempt: pressing Pin during a run that had
    ; to position the window would find the window filling the opening (because that run put it
    ; there), flip the flag, and switch this lock off underneath the run. Whether the lock runs is
    ; decided once, where it is decided, by the SetTimer above.
    winCrit := "ahk_exe " LockedProcess
    hwnd := WinExist(winCrit)
    if !hwnd
        return
    hole := GetHoleRect()
    ; The game can be restarted under a running macro (a disconnect reconnects it), and the
    ; replacement window arrives with its own frame. Re-applying here rather than only in
    ; ForceGameWindow is what stops it coming back with a title bar mid-run. Cheap to repeat: it
    ; returns immediately once the window is already borderless.
    ;
    ; Called unconditionally, NOT only while the option is on, because its off-path is what puts a
    ; title bar back. Unticking the box mid-run would otherwise leave the window borderless until
    ; the next stop, since this timer is the only thing touching it while a macro runs.
    ApplyBorderlessGameWindow(hwnd)
    try {
        GetVisibleFrameGaps(hwnd, &lg, &tg, &rg, &bg)
        targetX := hole.x - lg
        targetY := hole.y - tg
        targetW := hole.w + lg + rg
        targetH := hole.h + tg + bg
        WinGetPos &cx, &cy, &cw, &ch, "ahk_id " hwnd
        if (cx != targetX || cy != targetY || cw != targetW || ch != targetH)
            WinMove targetX, targetY, targetW, targetH, "ahk_id " hwnd
    }
}

; Brings the locked game window back to the foreground. Needed after shelling out to
; PowerShell for OCR, since that can steal keyboard/window focus (even hidden) and cause
; Send (inventory hotkeys) to go to the wrong window while Click still visually works.
ReactivateGameWindow() {
    global LockedProcess
    if (LockedProcess = "")
        return
    winCrit := "ahk_exe " LockedProcess
    if WinExist(winCrit)
        WinActivate winCrit
}

; ============================================================
; DISCONNECT DETECTION (AUTO-RECONNECT)
; ============================================================
; Runs on its own timer the whole time the macro is running, independently of whatever step is
; currently executing. Once every configured interval, scans the configured region for the
; configured "disconnected" text; if found, reconnects through the configured private-server link
; when it has one, otherwise clicks the Reconnect Button position and asks
; StartMacro() to restart the current preset from the beginning (via DisconnectRestartPending) -
; the same way Escape already stops the run asynchronously mid-step, just auto-resuming afterward
; instead of staying stopped. Uses its own OCR output file (ocr_result_disconnect.txt) so a scan
; firing here never races with a step's own OCR call (e.g. Round End Detection) that might be in
; progress on the main thread at the same moment.
IsPrivateServerLink(link) {
    ; Run opens the configured text directly, so only accept Roblox HTTPS hosts and fail closed.
    ; Kept in step with validation_error() in gui/app/private_server_link.py deliberately: the GUI
    ; refuses to save anything this would reject, so the two accepting different sets would only
    ; show up through a hand-edited config.ini, which is exactly the case this guard exists for.
    ; Host first, then the link shape (a share link, or the older private server link code).
    link := Trim(link)
    if (link = "")
        return false
    ; Host is matched case-insensitively (DNS is), everything below case-sensitively, because the
    ; Python side compares the path and the query values exactly and the two must not drift apart.
    ; Each code must also be non-empty, matching that side's own "is this value truthy" checks.
    if !RegExMatch(link, "i)^https://(?:[a-z0-9-]+\.)*roblox\.com(?::[0-9]+)?(?:[/?#]|$)")
        return false
    if RegExMatch(link, "[?&]privateServerLinkCode=[^&#]")
        return true
    return RegExMatch(link, "^(?i:https://[^/?#]+)/share(?:[?#]|$)")
        && RegExMatch(link, "[?&]code=[^&#]")
        && RegExMatch(link, "[?&]type=Server(?:[&#]|$)")
}

CheckDisconnectTick() {
    global Running, DisconnectCheckBusy, DisconnectLastCheckTick, DisconnectRestartPending, OcrBusy, StopRequested

    ; Skip if a main-thread OCR request is in flight - both share the one OCR server's request/
    ; response files, so we let the current scan finish and try again on the next tick instead.
    if (!Running || DisconnectCheckBusy || OcrBusy || !SafeInt(Cfg("General", "DisconnectEnabled", 0)))
        return

    intervalMs := Max(1000, SafeInt(Cfg("General", "DisconnectIntervalSec", 5), 5) * 1000)
    if (A_TickCount - DisconnectLastCheckTick < intervalMs)
        return
    DisconnectLastCheckTick := A_TickCount

    expected := Cfg("General", "DisconnectText", "")
    a := AbsXY(Cfg("General", "DisconnectX1", 0), Cfg("General", "DisconnectY1", 0))
    b := AbsXY(Cfg("General", "DisconnectX2", 0), Cfg("General", "DisconnectY2", 0))
    rect := {x: Min(a.x, b.x), y: Min(a.y, b.y), w: Abs(b.x - a.x), h: Abs(b.y - a.y)}
    if (expected = "" || rect.w <= 0 || rect.h <= 0)
        return

    DisconnectCheckBusy := true
    text := RunOcrOnRegion(rect.x, rect.y, rect.w, rect.h)
    if (text = "" || !(InStr(text, expected) || TextContainsPartialMatch(text, expected, 6))) {
        DisconnectCheckBusy := false
        return
    }

    privateServerLink := Trim(Cfg("General", "PrivateServerLink", ""))
    if (privateServerLink != "" && IsPrivateServerLink(privateServerLink)) {
        LogMsg("Disconnect detected -> rejoining through the configured private server link.")
        proc := ConfiguredGameProcess()
        gameCrit := "ahk_exe " proc
        hadGameWindow := (proc != "" && WinExist(gameCrit))
        try Run privateServerLink
        ; A disconnect leaves Roblox in one of two quite different states, so the wait differs.
        ; If Roblox is gone entirely, its window has to come back before anything else can happen,
        ; so wait for it. In the usual case it is still running, sitting on its own disconnect
        ; dialog (that dialog is what the OCR scan above just read), so its window already exists
        ; and waiting for it would return instantly and prove nothing. There, the only useful wait
        ; is a short settle giving the browser handoff and the teleport time to start.
        ; Neither wait tries to detect that the private server has finished LOADING. The restart
        ; below re-runs the preset from its first screen, and that screen detection is what waits
        ; for the game to really be ready, exactly as it already does on the Reconnect click path.
        if (!hadGameWindow && proc != "") {
            waitUntil := A_TickCount + 30000
            while (A_TickCount < waitUntil && !StopRequested && !WinExist(gameCrit))
                Sleep 500
        }
        settleUntil := A_TickCount + 5000
        while (A_TickCount < settleUntil && !StopRequested)
            Sleep 250
    } else {
        if (privateServerLink != "")
            LogMsg("WARNING: configured private server link was ignored because it is not a roblox.com https link.")
        ReactivateGameWindow()
        LogMsg("Disconnect detected -> clicking Reconnect and restarting from the beginning.")
        rc := AbsXY(Cfg("General", "DisconnectReconnectX", 0), Cfg("General", "DisconnectReconnectY", 0))
        ActClick(rc.x, rc.y)
    }
    Running := false
    DisconnectRestartPending := true
    DisconnectCheckBusy := false
}
SetTimer(CheckDisconnectTick, 500)

; Moves the game window into the opening. Also ensures the gray/log/stats overlay is showing,
; unless showOverlay is false (used by Pin, which only wants the window itself moved, nothing else
; appearing on screen). When enforceLock is true (an actual macro run), it additionally locks the
; window there so it can't be dragged or resized out of place by accident while the macro depends on
; fixed screen coordinates, and Escape claims the key system-wide so it can release that lock from
; anywhere. Pin passes enforceLock=false: a one-time move with no ongoing lock and nothing to
; release, so it never needs Escape.
ForceGameWindow(showOverlay := true, enforceLock := true) {
    global LockedProcess, GameWindowLeftToGame
    ; Cleared before either early return below, so the flag always describes THIS attempt. Left
    ; standing, a previous run's "left to the game" would go on wording Pin's message and silencing
    ; the lock timer for a call that never got as far as deciding anything.
    GameWindowLeftToGame := false
    proc := ConfiguredGameProcess()
    if (proc = "")
        return true  ; no process selected -> feature not in use, not an error

    winCrit := "ahk_exe " proc
    if !WinExist(winCrit) {
        LogMsg("WARNING: game window not found (" proc ").")
        return false
    }

    if showOverlay
        CreateOverlay()
    mayLeaveAlone := LeaveGameWindowGeometryAlone()

    ; WinRestore is a geometry change in disguise: on a maximized or full screen window it puts the
    ; window back to its old size, which is precisely the resize this must not do. Only a MINIMIZED
    ; window is restored on that path, since one left minimized cannot be clicked at all and would
    ; break the run outright. Off that path the unconditional restore stays as it was, because the
    ; move right below overrides whatever it did anyway.
    if mayLeaveAlone {
        try {
            if (WinGetMinMax(winCrit) = -1)
                WinRestore winCrit
        }
    } else {
        try WinRestore winCrit
    }
    ; Activating is NOT geometry and stays unconditional: Send goes to whatever window has the
    ; keyboard focus, so a run that skipped this would type into something else. Only the
    ; move/resize/frame work below is what a background session must not do.
    WinActivate winCrit
    Sleep 200
    hwnd := WinExist(winCrit)
    ; The decision, as opposed to the policy: the geometry is only left to the game once the game is
    ; measurably already filling the opening. Asking Roblox to start full screen happens in another
    ; process and can quietly fail, and a run that clicked full screen coordinates at a windowed
    ; client would be wrong in every single step.
    leaveAlone := mayLeaveAlone && hwnd && GameWindowFillsOpening(hwnd)
    ; hwnd is part of the condition so this only claims a positioning that is about to happen: a
    ; window that vanished between the check above and here is a different story, and the block below
    ; skips it too.
    if (mayLeaveAlone && !leaveAlone && hwnd)
        LogMsg("Game window is not filling the screen, so it was positioned as usual (" proc ").")
    GameWindowLeftToGame := leaveAlone
    if (hwnd && !leaveAlone) {
        if mayLeaveAlone {
            ; Only reached on the fallback: the restore above deliberately skipped a MAXIMIZED
            ; window, since un-maximizing one is itself the resize this feature exists to avoid. Now
            ; that this is positioning after all, it has to happen, or WinMove would be working
            ; against a window Windows still considers maximized. The Sleep gives it the same
            ; settling time the normal path gets from its own WinActivate/Sleep pair, so the frame
            ; measurement below reads a window that has finished changing shape.
            try WinRestore winCrit
            Sleep 200
        }
        hole := GetHoleRect()
        DisableRoundedCorners(hwnd)
        ; Before the move, not after: removing the caption changes the frame the move has to
        ; compensate for, so measuring the gaps first would compensate for a frame that is gone.
        ApplyBorderlessGameWindow(hwnd)
        MoveWindowToVisibleRect(hwnd, hole.x, hole.y, hole.w, hole.h)
    }

    if enforceLock {
        ; LockedProcess is claimed either way. It is not only the lock timer's input: it is what
        ; ReactivateGameWindow() brings back to the front after an OCR call stole focus, and what
        ; the Escape guard reads to know a run has something to release. Both still apply here.
        ; Only the twice-a-second snap-back is skipped, because there is nowhere to snap the window
        ; back TO that the game is not already filling by itself.
        LockedProcess := proc
        ; Turned OFF explicitly rather than merely not turned on. A restart (a disconnect reconnect
        ; or a preset switch) reaches this without CloseOverlay in between, so a lock left running by
        ; a previous run that had to position the window would otherwise go on snapping a window this
        ; run just decided not to own. Deciding and starting/stopping the timer in the same place is
        ; what keeps the two from drifting apart.
        SetTimer EnforceWindowLock, leaveAlone ? 0 : 500
    }
    if leaveAlone
        LogMsg("Game window activated; its size and position are left to the game (background session, fullscreen opening) (" proc ").")
    else if enforceLock
        LogMsg("Game window positioned and locked (" proc ").")
    else
        LogMsg("Game window positioned (" proc ").")
    return true
}

; Pin keeps working in a background session rather than becoming a no-op, but it pins what there is
; left to pin: the window is brought to the front and nothing else. Refusing outright would be worse
; on both counts, since the caller (the hotkey, or the GUI's own button through the local bridge's
; FORCE_GAME_WINDOW verb) asked for something explicitly and the coordinates it exists to support are
; still recorded against the same opening. Saying which of the two happened is the point of the
; separate message: reporting "positioned" for a window nothing moved is how a user ends up hunting
; a bug that is a deliberate behaviour.
PinClick(*) {
    ClearLog()
    ok := ForceGameWindow(false, false)
    if (ok && GameWindowGeometryWasLeftToGame())
        LogMsg("Pin: window brought to the front; it is already full screen and is left that way. Use the Set Position buttons to record coordinates.")
    else if ok
        LogMsg("Pin: window positioned. Use the Set Position buttons to record coordinates.")
    else
        LogMsg("Pin: could not position the game window.")
    return ok
}

F7::PinClick()

; ============================================================
; PAUSE / STOP
; ============================================================
F9:: {
    global Paused
    Paused := !Paused
    LogMsg(Paused ? "Paused." : "Resumed.")
}

; Cancels a pending Python field-id point capture (see BeginFieldCapture), publishing a
; cancelled result and restoring MarkerGui exactly like the Escape hotkey always has.
; Pulled out of Escape:: so a non-hotkey caller (the local bridge's CANCEL_CAPTURE verb) can
; trigger the identical cleanup instead of duplicating it - mirrors CancelRegionCapture().
CancelFieldCapture() {
    global FieldCaptureId, MarkerGui
    WriteFieldCaptureResult(FieldCaptureId, true)
    FieldCaptureId := ""
    SetTimer UpdateMarkerPos, 0
    try MarkerGui.Hide()
    ToolTip()
    LogMsg("Position capture cancelled.")
}

; Guards the Escape hotkey so it only claims the key while there is actually something to cancel or
; stop (a capture in progress, or the game window locked/overlaid by a running macro - including the
; brief gap between MainLoop returning and StartMacro re-setting Running, see the STOP comment
; below); otherwise AHK does not register the hotkey at all and Escape reaches whatever other
; application has focus. Pin no longer sets OverlayVisible/LockedProcess (see ForceGameWindow's
; enforceLock parameter), so being pinned alone no longer claims Escape.
EscapeHasSomethingToCancel() {
    global Running, OverlayVisible, RegionCapActive, FieldCaptureId, LockedProcess
    return RegionCapActive || (FieldCaptureId != "") || OverlayVisible
        || (LockedProcess != "") || Running
}

#HotIf EscapeHasSomethingToCancel()
Escape:: {
    global Running, OverlayVisible, RegionCapActive
    global PendingPresetSwitch, PresetSwitchRestartPending, StopRequested
    global FieldCaptureId, LockedProcess
    if RegionCapActive {
        CancelRegionCapture()
        return
    }
    if (FieldCaptureId != "") {
        CancelFieldCapture()
        return
    }
    ; LockedProcess is checked in addition to OverlayVisible because a real run's window lock can
    ; outlive Running going false for a moment (the restart gap above), and needs releasing too.
    if (OverlayVisible || LockedProcess != "")
        CloseOverlay()
    ; Reached only when Escape is acting as a STOP - the capture-cancel cases above return first (that
    ; is Escape's documented priority: cancel an in-progress capture, then a second press stops). Here
    ; it cancels any queued/committed preset switch AND latches StopRequested, whether or not Running is
    ; still true, so it also aborts a disconnect or preset-switch restart caught between MainLoop
    ; returning and StartMacro re-setting Running:=true. StopRequested is deliberately NOT set on a bare
    ; capture-cancel: a latch set mid-run would wrongly abort a LATER restart in the same session (the
    ; "am I mid-restart?" state isn't observable here - both restart flags are already consumed by the
    ; time ForceGameWindow runs). It is reset at the next StartMacro entry.
    PendingPresetSwitch := ""
    PresetSwitchRestartPending := false
    StopRequested := true
    if Running {
        Running := false
        LogMsg("EMERGENCY STOP: macro stopped.")
    }
}
#HotIf

F10::StartMacroWithLocalFeedback()

; ============================================================
; LOGGING
; ============================================================
; Formats a number with exactly 2 decimal places, so every duration in the log reads consistently
; (0.5 -> "0.50", 3 -> "3.00").
Fmt2(n) {
    return Format("{:.2f}", n + 0)
}

; Collapses OCR-recognized text to a single short line for the log - runs of whitespace/newlines
; become one space, it's trimmed, and long results are cut with an ellipsis - so a multi-line or
; long scan result stays one tidy line instead of flooding the panel.
OcrPreview(text, maxLen := 45) {
    s := Trim(RegExReplace(text, "\s+", " "))
    if (s = "")
        return "(nothing recognized)"
    if (StrLen(s) > maxLen)
        s := SubStr(s, 1, maxLen) "..."
    return s
}

; Clears the in-memory/on-screen log (not the log FILE, which stays a full history across runs) -
; called whenever a fresh run starts (macro or Pin) so the panel only shows this run.
ClearLog() {
    global LogLines
    LogLines := []
    RenderLogPanel()
}

LogMsg(text) {
    global LogFile, LogLines, DryRun
    timestamp := FormatTime(, "yyyy-MM-dd HH:mm:ss")
    line := timestamp " - " (DryRun ? "[DRY] " : "") text
    try FileAppend line "`n", LogFile

    ; Keep only the most recent lines so memory/display don't grow unbounded over a long run.
    LogLines.Push(line)
    maxLines := 200
    while (LogLines.Length > maxLines)
        LogLines.RemoveAt(1)

    RenderLogPanel()
}

; Updates the most recent log line IN PLACE instead of appending a new one, and does NOT write
; to the log file. Used for live-ticking status (e.g. a countdown while waiting) so it doesn't
; spam the log with one line per tick - only the final LogMsg() call after the wait is permanent.
LogMsgReplace(text) {
    global LogLines, DryRun
    timestamp := FormatTime(, "yyyy-MM-dd HH:mm:ss")
    line := timestamp " - " (DryRun ? "[DRY] " : "") text

    if (LogLines.Length = 0)
        LogLines.Push(line)
    else
        LogLines[LogLines.Length] := line

    RenderLogPanel()
}

RenderLogPanel() {
    global LogEdit, LogLines
    if (LogEdit = "")
        return
    try {
        display := ""
        for l in LogLines
            display .= l "`n"
        LogEdit.Value := display
        ; scroll to bottom (WM_VSCROLL / SB_BOTTOM)
        PostMessage 0x0115, 7, 0, , "ahk_id " LogEdit.Hwnd
    }
}

; Waits `seconds`, showing a live countdown in the log, and returns as soon as that time elapses OR
; the macro is stopped. The countdown text refreshes only ~4x/second (250ms) rather than the old
; every-10ms loop - updating the log panel 100x/second just to tick a countdown re-rendered the
; whole panel constantly and was a real source of visible lag during waits. Stop latency stays low
; because the actual Sleep is capped at 100ms per slice.
WaitSecondsInterruptible(seconds, msgPrefix) {
    global Running
    if (seconds <= 0)
        return
    endTick := A_TickCount + Round(seconds * 1000)
    nextDisplayTick := 0
    while Running {
        remainingMs := endTick - A_TickCount
        if (remainingMs <= 0)
            break
        if (A_TickCount >= nextDisplayTick) {
            LogMsgReplace(msgPrefix Fmt2(remainingMs / 1000) "s...")
            nextDisplayTick := A_TickCount + 250
        }
        Sleep (remainingMs < 100 ? remainingMs : 100)
    }
}

; Applies the overlay's dark theme (black background, white text) to a ListView control - AHK's
; ListView defaults to a white background/black text, which would stand out against every other
; panel in this overlay. LVM_SETBKCOLOR/LVM_SETTEXTCOLOR/LVM_SETTEXTBKCOLOR (0x1001/0x1024/0x1026).
StyleOverlayListView(lv) {
    black := 0x000000
    white := 0xFFFFFF
    SendMessage(0x1001, 0, black, , "ahk_id " lv.Hwnd)
    SendMessage(0x1024, 0, white, , "ahk_id " lv.Hwnd)
    SendMessage(0x1026, 0, black, , "ahk_id " lv.Hwnd)
}

; A_TickCount wraps to 0 after ~49.7 days of system uptime, which a farming session left running
; unattended can plausibly exceed. Session/screen/step time accumulate across a single run for as
; long as that run lasts, so - unlike the file's other short-lived A_TickCount timers (waits,
; timeouts measured in seconds) - they are exactly the kind of long-lived duration a wraparound
; would corrupt. GetTickCount64 is a 64-bit monotonic ms counter that does not wrap in any
; realistic uptime, so all of this feature's timers use it instead of A_TickCount.
Now64() {
    return DllCall("GetTickCount64", "Int64")
}

; Formats a millisecond duration as H:MM:SS (or MM:SS under an hour).
FormatDurationMs(ms) {
    if (ms < 0)
        ms := 0
    totalSec := Integer(ms / 1000)
    h := totalSec // 3600
    m := Mod(totalSec // 60, 60)
    s := Mod(totalSec, 60)
    return h > 0 ? Format("{:d}:{:02d}:{:02d}", h, m, s) : Format("{:d}:{:02d}", m, s)
}

; Refreshes the "Screen Time" table - one row per screen in the currently running preset, showing
; cumulative time spent so far THIS run (see ScreenTimeMs; it resets every MainLoop() call, same
; scope as ScreenRunCounts). Safe to call even when the overlay/panel doesn't exist, or before
; PresetScreens has been built yet.
RenderTimeBreakdownPanel() {
    global ScreenTimeLV, PresetScreens
    if (ScreenTimeLV = "")
        return
    try {
        ScreenTimeLV.Delete()
        for scr in PresetScreens {
            total := LiveScreenTimeMsFor(scr.Name)
            ScreenTimeLV.Add(, scr.Name, FormatDurationMs(total))
        }
    }
}

; Cumulative time for `screenName` so far this session, including the live in-progress elapsed
; time if it is the currently running screen (see ScreenTimeMs - only flushed on screen exit, so
; without this the actively running screen would read 0/stale for its entire duration).
LiveScreenTimeMsFor(screenName) {
    global ScreenTimeMs, RunningScreenName, ScreenEnterTick
    total := ScreenTimeMs.Has(screenName) ? ScreenTimeMs[screenName] : 0
    if (screenName = RunningScreenName && RunningScreenName != "")
        total += Now64() - ScreenEnterTick
    return total
}

; Same as LiveScreenTimeMsFor, but returns the whole map at once (screen name -> cumulative ms,
; including the currently running screen's live elapsed) - used by the bridge writers so
; remote_status.json/local_status.json never publish a stale/zero value for the active screen.
LiveScreenTimeMsSnapshot() {
    global ScreenTimeMs, RunningScreenName, ScreenEnterTick
    result := Map()
    for k, v in ScreenTimeMs
        result[k] := v
    if (RunningScreenName != "") {
        prevMs := result.Has(RunningScreenName) ? result[RunningScreenName] : 0
        result[RunningScreenName] := prevMs + (Now64() - ScreenEnterTick)
    }
    return result
}

; Same idea as LiveScreenTimeMsSnapshot, for StepTimeMs/CurrentStepKey.
StepTimeMsSnapshot() {
    global StepTimeMs, CurrentStepKey, StepCurrentStartTick
    result := Map()
    for k, v in StepTimeMs
        result[k] := v
    if (CurrentStepKey != "") {
        prevMs := result.Has(CurrentStepKey) ? result[CurrentStepKey] : 0
        result[CurrentStepKey] := prevMs + (Now64() - StepCurrentStartTick)
    }
    return result
}

; Cumulative time for the active step so far this session, including its live in-progress elapsed
; time. Deliberately the ACCUMULATIVE total across every attempt at that step this run (the value
; the removed "Step Time" table showed in its Total column), not just the current attempt's elapsed
; time, so a repeating step keeps counting up instead of restarting from zero on every repetition.
; Returns -1 when no step is currently running so callers can display a placeholder.
LiveCurrentStepTimeMs() {
    global StepTimeMs, CurrentStepKey, StepCurrentStartTick
    if (CurrentStepKey = "")
        return -1
    prevMs := StepTimeMs.Has(CurrentStepKey) ? StepTimeMs[CurrentStepKey] : 0
    return prevMs + (Now64() - StepCurrentStartTick)
}

; Puts the Application Stats panel's current values on the clipboard - same rationale as needed
; anywhere in this NOACTIVATE overlay (see CreateOverlay): its controls can't get real keyboard
; focus, so click-to-select + Ctrl+C doesn't work reliably; a button click does.
CopyStatsClick(*) {
    global ScreenRepeatCount, LastDetectedMap, RunningScreenName, RunningStepDescription
    global StepRepeatCount, StartRepeatCount, VictoryCount, DefeatCount, SessionStartTick
    stepMs := LiveCurrentStepTimeMs()
    text := "Screen Repetition Count: " ScreenRepeatCount "`n"
        . "Current Map: " (LastDetectedMap != "" ? LastDetectedMap : "(none)") "`n"
        . "Current Screen: " (RunningScreenName != "" ? RunningScreenName : "-") "`n"
        . "Current Step: " (RunningStepDescription != "" ? RunningStepDescription : "-") "`n"
        . "Step Repetition Count: " StepRepeatCount "`n"
        . "Session Time: " FormatDurationMs(Now64() - SessionStartTick) "`n"
        . "Current Step Time: " (stepMs >= 0 ? FormatDurationMs(stepMs) : "-") "`n"
        . "Start Repetition Count: " StartRepeatCount "`n"
        . "Victory Count: " VictoryCount "`n"
        . "Defeat Count: " DefeatCount
    A_Clipboard := text
    ToolTip("Stats copied to clipboard.")
    SetTimer((*) => ToolTip(), -1500)
}

; Refreshes the "Application Stats" panel below the log with the current run's live state.
; Safe to call even when the overlay/panel doesn't exist (e.g. before the macro is started).
RenderStatsPanel() {
    global StatsMapText, StatsScreenText, StatsStepText
    global StatsStepRepeatText, StatsStartRepeatText, StatsVictoryText, StatsDefeatText
    global StatsSessionTimeText, StatsCurrentStepTimeText
    global LastDetectedMap, RunningScreenName, RunningStepDescription
    global StepRepeatCount, StartRepeatCount, VictoryCount, DefeatCount, SessionStartTick
    if (StatsMapText = "")
        return
    SetStatText(StatsMapText, "map", LastDetectedMap != "" ? LastDetectedMap : "(none)")
    SetStatText(StatsScreenText, "screen", RunningScreenName != "" ? RunningScreenName : "-")
    SetStatText(StatsStepText, "step", RunningStepDescription != "" ? RunningStepDescription : "-")
    SetStatText(StatsStepRepeatText, "steprep", StepRepeatCount)
    SetStatText(StatsSessionTimeText, "sessiontime", FormatDurationMs(Now64() - SessionStartTick))
    stepMs := LiveCurrentStepTimeMs()
    SetStatText(StatsCurrentStepTimeText, "currentsteptime", stepMs >= 0 ? FormatDurationMs(stepMs) : "-")
    SetStatText(StatsStartRepeatText, "startrep", StartRepeatCount)
    SetStatText(StatsVictoryText, "victory", VictoryCount)
    SetStatText(StatsDefeatText, "defeat", DefeatCount)
}

; Writes `val` to a stats control only if it differs from what was last written there - each stats
; row is refreshed on every step, but most rows only change occasionally, so skipping no-op updates
; avoids pointless WM_SETTEXT/repaint work. StatsLastVals is cleared whenever the panel is rebuilt.
SetStatText(ctrl, key, val) {
    global StatsLastVals
    s := String(val)
    if (StatsLastVals.Has(key) && StatsLastVals[key] == s)
        return
    StatsLastVals[key] := s
    try ctrl.Text := s
}

; ============================================================
; SAVE CONFIGURATION
; ============================================================
; Snapshots the current config.ini into a rotating set of timestamped backups (config_backups\)
; before it gets overwritten. config.ini is a single binary file holding EVERY preset, map profile
; and setting, so one bad/interrupted save could otherwise wipe all of it - a cheap copy first is
; insurance. Keeps the most recent `keep` snapshots and prunes older ones. Best-effort: any failure
; here is swallowed so it can never block an actual save.
BackupConfig() {
    global ConfigFile, DataDir
    try {
        if !FileExist(ConfigFile)
            return
        backupDir := DataDir "\config_backups"
        if !DirExist(backupDir)
            DirCreate backupDir
        FileCopy ConfigFile, backupDir "\config_" FormatTime(, "yyyyMMdd_HHmmss") ".ini", 1

        keep := 10
        names := ""
        Loop Files backupDir "\config_*.ini"
            names .= A_LoopFileName "`n"
        names := Trim(names, "`n")
        if (names = "")
            return
        ; The yyyyMMdd_HHmmss stamp makes plain name order match chronological order (oldest first).
        arr := StrSplit(Sort(names), "`n")
        while (arr.Length > keep)
            try FileDelete backupDir "\" arr.RemoveAt(1)
    }
}

; Snapshots the General tab's control values as plain data for SaveGeneralFromData().

; Writes exactly the flat [General] fields from a plain data object. Preset/map-profile sections,
; list/active pointers, and backup policy remain the responsibility of SaveConfig().


; ============================================================
; PRESET MANAGEMENT
; ============================================================
; Reads a preset's ordered list of screen names.

; Position (1-based) of `screenName` in `name`'s screen list, or 0 if not found.

; Reads one screen's steps by index (used by both the editor and the running macro).
BuildScreenStepsFromIni(name, screenIdx) {
    section := GamePresetSection(name)
    n := Integer(Cfg(section, "Screen" screenIdx "StepCount", "0"))
    arr := []
    Loop n {
        i := A_Index
        arr.Push({Type: Cfg(section, "Screen" screenIdx "Step" i "Type", "Button Click"),
            Label: Cfg(section, "Screen" screenIdx "Step" i "Label", ""),
            X: Cfg(section, "Screen" screenIdx "Step" i "X", "0"),
            Y: Cfg(section, "Screen" screenIdx "Step" i "Y", "0"),
            EndX: Cfg(section, "Screen" screenIdx "Step" i "EndX", "0"),
            EndY: Cfg(section, "Screen" screenIdx "Step" i "EndY", "0"),
            DragMs: Cfg(section, "Screen" screenIdx "Step" i "DragMs", "500"),
            OncePerCycle: Integer(Cfg(section, "Screen" screenIdx "Step" i "OncePerCycle", "0")),
            AlreadyDone: false,
            Seconds: Cfg(section, "Screen" screenIdx "Step" i "Seconds", "0"),
            OnTrueScreen: Cfg(section, "Screen" screenIdx "Step" i "OnTrueScreen", "(continue)"),
            OnFalseScreen: Cfg(section, "Screen" screenIdx "Step" i "OnFalseScreen", "(continue)"),
            FallbackEnabled: Integer(Cfg(section, "Screen" screenIdx "Step" i "FallbackEnabled", "0")),
            FallbackMaxAttempts: Cfg(section, "Screen" screenIdx "Step" i "FallbackMaxAttempts", "5"),
            FallbackScreen: Cfg(section, "Screen" screenIdx "Step" i "FallbackScreen", "(none)"),
            FallbackAttemptCount: 0,
            Advanced: Integer(Cfg(section, "Screen" screenIdx "Step" i "Advanced", "0")),
            OutcomesRaw: Cfg(section, "Screen" screenIdx "Step" i "Outcomes", "")})
    }
    return arr
}


; Writes one screen's full data (name + steps) at the given index. Used for saves, reordering,
; and rebuilding after a delete.
WriteScreenSteps(name, idx, screenName, steps) {
    global ConfigFile
    section := GamePresetSection(name)
    IniWrite screenName, ConfigFile, section, "Screen" idx "Name"
    IniWrite steps.Length, ConfigFile, section, "Screen" idx "StepCount"
    for j, st in steps {
        IniWrite st.Type, ConfigFile, section, "Screen" idx "Step" j "Type"
        IniWrite st.Label, ConfigFile, section, "Screen" idx "Step" j "Label"
        IniWrite st.X, ConfigFile, section, "Screen" idx "Step" j "X"
        IniWrite st.Y, ConfigFile, section, "Screen" idx "Step" j "Y"
        IniWrite st.EndX, ConfigFile, section, "Screen" idx "Step" j "EndX"
        IniWrite st.EndY, ConfigFile, section, "Screen" idx "Step" j "EndY"
        IniWrite st.DragMs, ConfigFile, section, "Screen" idx "Step" j "DragMs"
        IniWrite (st.OncePerCycle ? 1 : 0), ConfigFile, section, "Screen" idx "Step" j "OncePerCycle"
        IniWrite st.OnTrueScreen, ConfigFile, section, "Screen" idx "Step" j "OnTrueScreen"
        IniWrite st.OnFalseScreen, ConfigFile, section, "Screen" idx "Step" j "OnFalseScreen"
        IniWrite st.Seconds, ConfigFile, section, "Screen" idx "Step" j "Seconds"
        IniWrite (st.FallbackEnabled ? 1 : 0), ConfigFile, section, "Screen" idx "Step" j "FallbackEnabled"
        IniWrite st.FallbackMaxAttempts, ConfigFile, section, "Screen" idx "Step" j "FallbackMaxAttempts"
        IniWrite st.FallbackScreen, ConfigFile, section, "Screen" idx "Step" j "FallbackScreen"
        IniWrite (st.Advanced ? 1 : 0), ConfigFile, section, "Screen" idx "Step" j "Advanced"
        IniWrite st.OutcomesRaw, ConfigFile, section, "Screen" idx "Step" j "Outcomes"
    }
}

; Reads one legacy phase's steps (old flat "BeforeCount"/"BeforeStep{i}..." format, no
; OnTrue/OnFalseScreen yet) - only used during the one-time migration to Screens below.
MigrateLegacyPhaseSteps(psection, prefix) {
    n := Integer(Cfg(psection, prefix "Count", "0"))
    arr := []
    Loop n {
        i := A_Index
        arr.Push({Type: Cfg(psection, prefix "Step" i "Type", "Button Click"),
            Label: Cfg(psection, prefix "Step" i "Label", ""),
            X: Cfg(psection, prefix "Step" i "X", "0"),
            Y: Cfg(psection, prefix "Step" i "Y", "0"),
            EndX: Cfg(psection, prefix "Step" i "EndX", "0"),
            EndY: Cfg(psection, prefix "Step" i "EndY", "0"),
            DragMs: Cfg(psection, prefix "Step" i "DragMs", "500"),
            OncePerCycle: Integer(Cfg(psection, prefix "Step" i "OncePerCycle", "0")),
            Seconds: Cfg(psection, prefix "Step" i "Seconds", "0"),
            OnTrueScreen: "(continue)",
            OnFalseScreen: "(continue)",
            FallbackEnabled: 0,
            FallbackMaxAttempts: "5",
            FallbackScreen: "(none)",
            Advanced: 0,
            OutcomesRaw: ""})
    }
    return arr
}

InitPresets() {
    global ConfigFile, PresetNames, CurrentPresetName, presetListBox, ActivePresetName

    presetListStr := Cfg(GamePresetsListSection(), "List", "")
    if (presetListStr = "") {
        ; First run: create a default "Challenges" preset with 3 screens (Before Map Detection ->
        ; Ingame -> Round End -> back to Before), the same routine the old fixed 3-phase system
        ; used to build automatically, just expressed as explicit screen jumps now.
        challengesSection := GamePresetSection("Challenges")
        IniWrite 3, ConfigFile, challengesSection, "ScreenCount"

        IniWrite "Before Map Detection", ConfigFile, challengesSection, "Screen1Name"
        IniWrite 4, ConfigFile, challengesSection, "Screen1StepCount"
        IniWrite "Option Select", ConfigFile, challengesSection, "Screen1Step1Type"
        IniWrite "Select Option", ConfigFile, challengesSection, "Screen1Step1Label"
        IniWrite "Button Click", ConfigFile, challengesSection, "Screen1Step2Type"
        IniWrite "Button 1", ConfigFile, challengesSection, "Screen1Step2Label"
        IniWrite "Detect Map", ConfigFile, challengesSection, "Screen1Step3Type"
        IniWrite "Detect Map", ConfigFile, challengesSection, "Screen1Step3Label"
        IniWrite "Ingame", ConfigFile, challengesSection, "Screen1Step3OnTrueScreen"
        IniWrite "Ingame", ConfigFile, challengesSection, "Screen1Step3OnFalseScreen"
        IniWrite "Button Click", ConfigFile, challengesSection, "Screen1Step4Type"
        IniWrite "Button 2", ConfigFile, challengesSection, "Screen1Step4Label"

        IniWrite "Ingame", ConfigFile, challengesSection, "Screen2Name"
        IniWrite 2, ConfigFile, challengesSection, "Screen2StepCount"
        IniWrite "Place Towers", ConfigFile, challengesSection, "Screen2Step1Type"
        IniWrite "Place Towers", ConfigFile, challengesSection, "Screen2Step1Label"
        IniWrite "Round End Detection", ConfigFile, challengesSection, "Screen2Step2Type"
        IniWrite "Victory", ConfigFile, challengesSection, "Screen2Step2Label"
        IniWrite "Round End", ConfigFile, challengesSection, "Screen2Step2OnTrueScreen"
        IniWrite "Ingame", ConfigFile, challengesSection, "Screen2Step2OnFalseScreen"

        IniWrite "Round End", ConfigFile, challengesSection, "Screen3Name"
        IniWrite 2, ConfigFile, challengesSection, "Screen3StepCount"
        IniWrite "Button Click", ConfigFile, challengesSection, "Screen3Step1Type"
        IniWrite "Button 3", ConfigFile, challengesSection, "Screen3Step1Label"
        IniWrite "Button Click", ConfigFile, challengesSection, "Screen3Step2Type"
        IniWrite "Button 4", ConfigFile, challengesSection, "Screen3Step2Label"

        IniWrite "Challenges", ConfigFile, GamePresetsListSection(), "List"
        IniWrite "Challenges", ConfigFile, GamePresetsListSection(), "Active"
        presetListStr := "Challenges"
    }

    PresetNames := StrSplit(presetListStr, ",")

    for n in PresetNames {
        psection := GamePresetSection(n)

        ; One-time migration: challenge options and the default-map fallback used to be global
        ; ([Option1]/[Option2]/[Option3] and [General] DefaultMap). Seed each preset that doesn't
        ; have its own copy yet from those old global values, so existing setups keep working.
        if (Cfg(psection, "Option1Name", "") = "") {
            Loop 3 {
                i := A_Index
                IniWrite Cfg("Option" i, "Name", "Option " i), ConfigFile, psection, "Option" i "Name"
                IniWrite Cfg("Option" i, "X", "0"), ConfigFile, psection, "Option" i "X"
                IniWrite Cfg("Option" i, "Y", "0"), ConfigFile, psection, "Option" i "Y"
                IniWrite Cfg("Option" i, "AvailableAtStart", "1"), ConfigFile, psection, "Option" i "Available"
                IniWrite Cfg("Option" i, "Priority", String(i)), ConfigFile, psection, "Option" i "Priority"
            }
            IniWrite Cfg("General", "DefaultMap", "(none)"), ConfigFile, psection, "DefaultMap"
        }

        ; One-time migration: presets used to have a single flat step list ("StepCount"/
        ; "Step{i}..."). If a preset still only has that (no phase data yet), move its whole
        ; step list into the "Before" phase as-is - it'll be picked up by the phase->Screens
        ; migration right below.
        oldStepCount := Cfg(psection, "StepCount", "")
        hasPhaseData := (Cfg(psection, "BeforeCount", "") != "" || Cfg(psection, "IngameCount", "") != "" || Cfg(psection, "RoundEndCount", "") != "")
        hasScreenData := (Cfg(psection, "ScreenCount", "") != "")
        if (oldStepCount != "" && !hasPhaseData && !hasScreenData) {
            IniWrite oldStepCount, ConfigFile, psection, "BeforeCount"
            Loop Integer(oldStepCount) {
                i := A_Index
                IniWrite Cfg(psection, "Step" i "Type", "Button Click"), ConfigFile, psection, "BeforeStep" i "Type"
                IniWrite Cfg(psection, "Step" i "Label", ""), ConfigFile, psection, "BeforeStep" i "Label"
                IniWrite Cfg(psection, "Step" i "X", "0"), ConfigFile, psection, "BeforeStep" i "X"
                IniWrite Cfg(psection, "Step" i "Y", "0"), ConfigFile, psection, "BeforeStep" i "Y"
                IniWrite Cfg(psection, "Step" i "Seconds", "0"), ConfigFile, psection, "BeforeStep" i "Seconds"
            }
            hasPhaseData := true
        }

        ; One-time migration: the old fixed 3-phase system (Before Map Detection / Ingame / Round
        ; End, chained via "AfterRoundEnd", with ONE shared OCR region per detection kind) is
        ; replaced by a flexible list of named Screens, each ending in explicit True/False jumps
        ; and each Logic step carrying its own OCR region. Convert any preset that still has old
        ; phase data but no Screen data yet.
        if (hasPhaseData && !hasScreenData) {
            beforeSteps := MigrateLegacyPhaseSteps(psection, "Before")
            ingameSteps := MigrateLegacyPhaseSteps(psection, "Ingame")
            roundEndSteps := MigrateLegacyPhaseSteps(psection, "RoundEnd")

            ; Detect Map (in Before) used the old global Map Text Detection region; give it that
            ; region and an unconditional continue to Ingame (matching the old automatic
            ; Before -> Ingame flow).
            for st in beforeSteps {
                if (st.Type = "Detect Map") {
                    st.X := Cfg("General", "RegionX1", "0")
                    st.Y := Cfg("General", "RegionY1", "0")
                    st.EndX := Cfg("General", "RegionX2", "0")
                    st.EndY := Cfg("General", "RegionY2", "0")
                    st.OnTrueScreen := "Ingame"
                    st.OnFalseScreen := "Ingame"
                }
            }
            ; Round End Detection (in Ingame, by convention the LAST step) used the old global
            ; Round End region/text; give it that region/text and reproduce the old
            ; repeat-until-true loop via explicit jumps.
            if (ingameSteps.Length > 0 && ingameSteps[ingameSteps.Length].Type = "Round End Detection") {
                last := ingameSteps[ingameSteps.Length]
                last.X := Cfg("General", "RoundEndX1", "0")
                last.Y := Cfg("General", "RoundEndY1", "0")
                last.EndX := Cfg("General", "RoundEndX2", "0")
                last.EndY := Cfg("General", "RoundEndY2", "0")
                last.Label := Cfg("General", "RoundEndText", "")
                last.OnTrueScreen := "Round End"
                last.OnFalseScreen := "Ingame"
            }

            ; Screen order determines the default fallthrough when a screen ends without an
            ; explicit jump - reproduce the old "AfterRoundEnd" dropdown by placing that target
            ; right after Round End in the list.
            afterRoundEnd := Cfg(psection, "AfterRoundEnd", "Before Map Detection")
            screens := (afterRoundEnd = "Ingame")
                ? [{Name: "Before Map Detection", Steps: beforeSteps}, {Name: "Round End", Steps: roundEndSteps}, {Name: "Ingame", Steps: ingameSteps}]
                : [{Name: "Before Map Detection", Steps: beforeSteps}, {Name: "Ingame", Steps: ingameSteps}, {Name: "Round End", Steps: roundEndSteps}]

            IniWrite screens.Length, ConfigFile, psection, "ScreenCount"
            for i, scr in screens
                WriteScreenSteps(n, i, scr.Name, scr.Steps)
        }
    }

    activeName := Cfg(GamePresetsListSection(), "Active", PresetNames[1])
    found := false
    for n in PresetNames {
        if (n = activeName)
            found := true
    }
    if !found
        activeName := PresetNames[1]

    CurrentPresetName := activeName
    ActivePresetName := activeName   ; the preset that runs on Start
}

; Updates the green "Runs on Start: <name>" indicator to match ActivePresetName.
UpdateActivePresetIndicator() {
    global activePresetText, ActivePresetName
    if (activePresetText != "")
        try activePresetText.Text := "Runs on Start: " (ActivePresetName != "" ? ActivePresetName : "-")
}

; Returns the 1-based index of a preset name in PresetNames (0 if not found).
PresetIndex(name) {
    global PresetNames
    for i, n in PresetNames {
        if (n = name)
            return i
    }
    return 0
}

; Local Start/F10 actions surface rejected startup results without interrupting the GUI or a future
; headless restart path. StartMacro itself only logs and returns its result contract.
StartMacroWithLocalFeedback(startScreen := "", startStep := 0, useActive := true) {
    result := StartMacro(startScreen, startStep, useActive)
    if !result.ok {
        ToolTip("Could not start:`n" result.msg)
        SetTimer((*) => ToolTip(), -3000)
    }
    return result
}

; The names of every screen in `name`'s preset, in list order.
GetPresetScreenNames(name) {
    section := GamePresetSection(name)
    n := Integer(Cfg(section, "ScreenCount", "0"))
    arr := []
    Loop n
        arr.Push(Cfg(section, "Screen" A_Index "Name", "Screen " A_Index))
    return arr
}

; ============================================================
; MACRO START
; ============================================================
; Reads every screen of a preset straight from ini, in list order, as an array of {Name, Steps}.
BuildAllScreensFromIni(name) {
    screens := []
    for i, screenName in GetPresetScreenNames(name)
        screens.Push({Name: screenName, Steps: BuildScreenStepsFromIni(name, i)})
    return screens
}

; startScreen/startStep let "Start Macro From This Step" begin execution partway into a specific
; screen instead of at the preset's normal start point; leave both at their defaults for a normal
; F10/Start-button run. Returns {ok, msg}: false for a rejected/failed startup, true after a normal stop.
StartMacro(startScreen := "", startStep := 0, useActive := true) {
    global Running, CurrentPresetName, PresetScreens, MapAdvStepsDoneThisCycle, RunningPresetName
    global DisconnectRestartPending, DisconnectLastCheckTick
    global ActivePresetName
    global PendingPresetSwitch, PresetSwitchRestartPending, ConfigFile, StopRequested, MacroActive
    global StartRepeatCount, VictoryCount, DefeatCount
    ; Reject a re-entry while a session is live, and claim the session + reset per-session state
    ; ATOMICALLY under Critical. Checking MacroActive (not just Running) also catches a Start/F10 pressed
    ; during the brief prep windows where Running is momentarily false (initial startup or a
    ; disconnect/preset-switch restart). Doing the claim AND the resets under Critical means (a) a
    ; re-entrant StartMacro cannot slip between the guard and MacroActive:=true, and (b) clearing
    ; StopRequested here only ever drops a STALE stop from a PRIOR session - a stop arriving after
    ; Critical "Off" latches for THIS session and is honored at the guarded check before Running:=true.
    ; The rejecting early return must NOT clear MacroActive (it belongs to the live session).
    Critical "On"
    if (Running || MacroActive) {
        Critical "Off"
        LogMsg("Already running.")
        return {ok: false, msg: "Already running."}
    }
    MacroActive := true
    ; Fresh run: drop any queued switch / stale stop from a previous session, and zero the
    ; lifetime-of-session stats counters (Start Repeat/Victory/Defeat) so a new run's Application
    ; Stats panel starts from zero instead of carrying over the previous run's numbers. This point
    ; runs exactly once per genuine new Start (F10 or the local IPC bridge's START command) and is
    ; NOT re-entered by StartMacro's own internal restart loop (disconnect auto-reconnect,
    ; a committed queued preset switch) - those continue the same session further down in the Loop
    ; body below, so they correctly keep accumulating into the same lifetime counts instead of
    ; resetting them. PendingPresetSwitch and PresetSwitchRestartPending can't actually be set this
    ; early (QUEUE_PRESET needs Running; the commit flag is only set at a cycle boundary), but
    ; clearing them keeps a clean slate.
    PendingPresetSwitch := ""
    PresetSwitchRestartPending := false
    StopRequested := false
    StartRepeatCount := 0
    VictoryCount := 0
    DefeatCount := 0
    Critical "Off"
    ; MacroActive now stays true for the whole session, INCLUDING restart prep (where Running is briefly
    ; false). The try/finally below guarantees it is cleared on EVERY exit - an early error return, a normal
    ; stop, a StopRequested abort, or an unexpected error mid-run - otherwise a stuck-true flag would (via
    ; the guard above) permanently block Start.
    try {
        ; Normal Start/F10 runs the ACTIVE preset (chosen via "Set as Active"), which may differ from the
        ; one currently being viewed. Switch the whole view over to it first, so the run reads the right
        ; preset's options/steps. "Start Macro From This Step" (useActive=false) runs the viewed preset.
        ; RunSteps() reads Cfg(presetSection, ...) via RunningPresetName directly, so CurrentPresetName
        ; is a plain pointer here now that the native editor GUI (which used to need a flush-and-reload
        ; of its own controls on every switch) is gone - see tasklist/open/major/python-owns-config.md.
        if (useActive && ActivePresetName != "" && ActivePresetName != CurrentPresetName && PresetIndex(ActivePresetName))
            CurrentPresetName := ActivePresetName
        ; DryRun has no live source of truth to read (the native GUI's checkbox that used to be it
        ; was never wired up to the Python side, and it was never persisted to config.ini - "not
        ; persisted (always off on launch)" per its own prior comment) - it just keeps its default
        ; `false` from here on, matching every launch of the shipped app already.
        ClearLog()
        if DryRun
            LogMsg("DRY RUN - actions are logged but NOT performed (no clicks/keys/drags).")

        ; Warm up the OCR helper now so the first detection step doesn't pay its one-time startup
        ; mid-run. Non-fatal if it can't start - detection falls back to the one-shot path.
        EnsureOcrServer()
        ; No-op unless the user has unzipped the experimental benchmark helper into
        ; RuntimeDir\ocr_benchmark (see EnsureOcrBenchmark); every normal production install never
        ; has that folder, so this line does nothing there.
        EnsureOcrBenchmark()

        ; Loops back to the top when Disconnect Detection (General tab) fired during the previous
        ; pass - restarting the current preset from its normal start point, same as pressing F10
        ; again, but automatic. A plain run (no disconnect) just executes this loop body once.
        curStartScreen := startScreen
        curStartStep := startStep
        isAutoRestart := false
        Loop {
            ; NOT SaveConfig(): that also re-derives [General]/the current preset/the current map
            ; profile from live native-GUI control values (BuildGeneralSaveData()/BuildPresetSaveData()/
            ; BuildMapProfileSaveData()), which exists only to flush a native GUI's unsaved edits before
            ; a run - the engine itself has no "unsaved GUI state" of its own, config.ini is already the
            ; single source of truth here (kept current by whichever explicit Save action last ran,
            ; native GUI or the local IPC bridge's SAVE_* verbs). Calling the full SaveConfig() from this
            ; headless run loop would silently overwrite whatever the IPC bridge just saved with stale
            ; GUI-control values every time a run starts. BackupConfig() alone still gives every run the
            ; same pre-run safety snapshot.
            BackupConfig()
            MapAdvStepsDoneThisCycle := false

            if !ForceGameWindow() {
                msg := "Could not find/position the game window. Check the selected process in the Timing tab, or click Refresh."
                LogMsg(msg)
                return {ok: false, msg: msg}
            }

            ; Read every screen straight from ini - it is already current, kept that way by whichever
            ; explicit Save action (native GUI or IPC) last ran, not by anything in this loop.
            PresetScreens := BuildAllScreensFromIni(CurrentPresetName)
            RunningPresetName := CurrentPresetName

            totalSteps := 0
            for scr in PresetScreens
                totalSteps += scr.Steps.Length
            if (PresetScreens.Length = 0 || totalSteps = 0) {
                msg := "The active preset has no steps in any screen. Add steps in Preset Settings > Edit first."
                LogMsg(msg)
                return {ok: false, msg: msg}
            }

            startScreenIdx := 0
            if (curStartScreen != "") {
                for i, scr in PresetScreens {
                    if (scr.Name = curStartScreen) {
                        startScreenIdx := i
                        break
                    }
                }
                if !startScreenIdx
                    LogMsg("WARNING: could not find screen '" curStartScreen "' to start from - using the normal start screen instead.")
            }

            ; Honor a stop that landed during the (re)start prep above (ForceGameWindow contains Sleeps, so
            ; a timer/hotkey stop can fire there after a disconnect or preset-switch restart was decided).
            ; Checking and flipping Running under Critical makes the two atomic, so a stop can never slip in
            ; between them and be overwritten by Running:=true.
            Critical "On"
            if StopRequested {
                Critical "Off"
                LogMsg("Stop requested during startup - not starting.")
                break
            }
            Running := true
            Critical "Off"
            DisconnectLastCheckTick := A_TickCount
            if isAutoRestart
                LogMsg("Auto-reconnect: macro restarted (preset '" CurrentPresetName "').")
            else if startScreenIdx
                LogMsg("Macro started (preset '" CurrentPresetName "', from screen '" curStartScreen "' step " curStartStep ").")
            else
                LogMsg("Macro started (preset '" CurrentPresetName "').")
            MainLoop(startScreenIdx, startScreenIdx ? Max(1, curStartStep) : 1)

            ; A queued preset switch (remote QUEUE_PRESET) that committed at a cycle boundary: switch the
            ; whole view over to the queued preset - exactly like the "Set as Active" switch at the top of
            ; this function - and loop again to run it from the top. Guarded by the commit flag, so only a
            ; real boundary switch triggers this, never a STOP that merely left a stale PendingPresetSwitch.
            if PresetSwitchRestartPending {
                PresetSwitchRestartPending := false
                newName := PendingPresetSwitch
                PendingPresetSwitch := ""
                if (newName != "" && PresetIndex(newName)) {
                    CurrentPresetName := newName
                    ActivePresetName := newName
                    ; The one persisted key a remote preset switch still needs to leave behind: which
                    ; preset a later restart of the whole app should show as active. Everything else this
                    ; branch used to also write (a full per-key rewrite of CurrentPresetName's own preset
                    ; section, via SavePresetToIni/BuildPresetSaveData) existed only to keep the native
                    ; editor GUI's own controls consistent, and is gone along with that GUI.
                    try IniWrite ActivePresetName, ConfigFile, GamePresetsListSection(), "Active"
                    LogMsg("Remote: switched to queued preset '" CurrentPresetName "'.")
                    curStartScreen := ""
                    curStartStep := 0
                    isAutoRestart := false
                    continue
                }
                LogMsg("Remote: queued preset no longer exists - staying stopped.")
            }

            if !DisconnectRestartPending
                break
            DisconnectRestartPending := false
            curStartScreen := ""
            curStartStep := 0
            isAutoRestart := true
        }
    } finally {
        ; Session ended by any path (normal stop, max-rounds, a stop that aborted a restart, an early error
        ; return, or an unexpected error) - always release the session flag.
        MacroActive := false
    }
    return {ok: true, msg: "Macro stopped."}
}

; ============================================================
; MAIN LOOP
; Walks the preset's Screens in list order. Each screen's Logic steps can jump execution straight
; to another screen (by name) via On True/On False; if a screen finishes without any jump firing,
; execution falls through to the next screen in the list, wrapping back to the first screen after
; the last. A "cycle" is considered complete every time execution returns to the first screen.
; ============================================================
; Finds which screen contains a "Start" component (if any) - that's where each cycle begins, and
; where the "cycle complete" bookkeeping (wait/save/max-rounds) fires when execution returns to
; it. Falls back to the first screen in the list if no "Start" component exists anywhere (the
; original always-start-at-the-top behavior), and warns if more than one was found.
FindStartScreenIndex(screens) {
    found := 0
    count := 0
    for i, scr in screens {
        for st in scr.Steps {
            if (st.Type = "Start") {
                count += 1
                if !found
                    found := i
            }
        }
    }
    if (count > 1)
        LogMsg("WARNING: multiple 'Start' components found - using the first one, on screen '" screens[found].Name "'.")
    return found ? found : 1
}

; startScreenIdx/startStepIdx: if startScreenIdx is nonzero, the FIRST screen executed is that one
; (starting partway in, at startStepIdx) instead of the preset's normal start screen - used by
; "Start Macro From This Step". Cycle-complete bookkeeping and wraparound always target the
; preset's real start screen (FindStartScreenIndex), regardless of where execution began, so an
; ad-hoc start doesn't disturb normal max-rounds/cycle-wait behavior once the macro catches up to
; the normal flow.
MainLoop(startScreenIdx := 0, startStepIdx := 1) {
    global Running, Paused, PresetScreens, RunningScreenName
    global ScreenRepeatCount, StepRepeatCount, StartRepeatCount, ScreenRunCounts, LastDetectedMap
    global PendingPresetSwitch, PresetSwitchRestartPending
    global SessionId, SessionStartTick, ScreenTimeMs, ScreenEnterTick
    global StepTimeMs, CurrentStepKey, StepCurrentStartTick

    trueStartIdx := FindStartScreenIndex(PresetScreens)
    screenIdx := startScreenIdx ? startScreenIdx : trueStartIdx
    cycleCount := 0
    ScreenRepeatCount := 0
    StepRepeatCount := 0
    ScreenRunCounts := Map()
    ; Session time / per-screen time / per-step time all reset here too, same scope as the
    ; counters above - every run start, including internal restarts (disconnect auto-reconnect, a
    ; committed queued preset switch). A fresh SessionId marks the boundary so the remote backend
    ; can tell this is a new session and archive whatever it last received as history.
    SessionId := Now64() "-" A_Now
    SessionStartTick := Now64()
    ScreenTimeMs := Map()
    ScreenEnterTick := Now64()
    StepTimeMs := Map()
    CurrentStepKey := ""
    StepCurrentStartTick := Now64()
    RunningScreenName := ""
    ; A leftover detected map from an earlier run/cycle must not keep overriding the configured
    ; Default Map forever - ResolveMapName() only falls back to Default Map when this is empty, so
    ; it needs clearing at the start of every fresh cycle (see the trueStartIdx block below), not
    ; just once here at the very start of the run.
    LastDetectedMap := ""
    firstIteration := true
    while Running {
        if Paused {
            Sleep 200
            continue
        }

        scr := PresetScreens[screenIdx]
        if (RunningScreenName != "") {
            prevMs := ScreenTimeMs.Has(RunningScreenName) ? ScreenTimeMs[RunningScreenName] : 0
            ScreenTimeMs[RunningScreenName] := prevMs + (Now64() - ScreenEnterTick)
        }
        RunningScreenName := scr.Name
        ScreenEnterTick := Now64()
        ScreenRunCounts[scr.Name] := (ScreenRunCounts.Has(scr.Name) ? ScreenRunCounts[scr.Name] : 0) + 1
        RenderTimeBreakdownPanel()
        stepStart := firstIteration ? startStepIdx : 1
        firstIteration := false
        jumpTarget := RunSteps(scr.Steps, stepStart)
        if !Running
            break

        if (jumpTarget != "") {
            nextIdx := 0
            for i, s in PresetScreens {
                if (s.Name = jumpTarget) {
                    nextIdx := i
                    break
                }
            }
            if !nextIdx {
                LogMsg("WARNING: screen '" jumpTarget "' not found - continuing to the next screen instead.")
                nextIdx := (screenIdx = PresetScreens.Length) ? trueStartIdx : screenIdx + 1
            } else {
                LogMsg("Jump: '" scr.Name "' -> '" jumpTarget "'.")
            }
        } else {
            nextIdx := (screenIdx = PresetScreens.Length) ? trueStartIdx : screenIdx + 1
        }
        screenIdx := nextIdx

        if (screenIdx = trueStartIdx) {
            cycleCount += 1
            ScreenRepeatCount := cycleCount
            StartRepeatCount += 1
            ; A new cycle starting means whatever map was detected last cycle no longer applies -
            ; clear it so ResolveMapName() falls back to the configured Default Map (if any) until
            ; a fresh "Detect Map" step (if this cycle has one) finds something again.
            LastDetectedMap := ""
            RenderStatsPanel()
            LogMsg("========== Cycle " cycleCount " complete (total starts: " StartRepeatCount ") ==========")

            ; A remote QUEUE_PRESET commits HERE, at the cycle boundary: hand off to StartMacro's
            ; restart loop (which switches to PendingPresetSwitch and runs it from the top), the same
            ; way DisconnectRestartPending does. The commit flag is set ONLY here - never on STOP or
            ; max-rounds - so a stop is never mistaken for a switch. Takes priority over the end-of-cycle
            ; wait and the old preset's Max cycles, since the user explicitly asked to move on.
            if (Running && PendingPresetSwitch != "") {
                PresetSwitchRestartPending := true
                Running := false
                break
            }

            extraWait := SafeNum(Cfg(GameSection(), "RoundWaitSeconds", "0"))
            if (extraWait > 0) {
                WaitSecondsInterruptible(extraWait, "Waiting before next cycle: ")
                LogMsg("Cycle wait complete.")
            }

            ; NOTE: the full config is deliberately NOT re-saved every cycle - it doesn't change
            ; during a run, and per-option "used today" counters already persist themselves the
            ; moment they change (see IncrementOptionUsed). Re-writing the entire config (every
            ; screen, step and map profile) each cycle was pure disk churn and caused lag on
            ; fast-cycling presets. Config is saved at macro start, on manual Save, and on exit.

            maxR := SafeInt(Cfg(GameSection(), "MaxRounds", "0"))
            if (maxR > 0 && cycleCount >= maxR) {
                LogMsg("Max cycles reached (" maxR ") - stopping.")
                Running := false
                break
            }
        }
    }
    ; If MainLoop is returning for any reason OTHER than a committed preset switch, drop any queued
    ; switch, so a leftover queue can neither leak into a later run nor keep showing in the status
    ; snapshot after the macro has stopped.
    if (!PresetSwitchRestartPending)
        PendingPresetSwitch := ""
    LogMsg("Macro stopped. Press F10 to start again.")
}

; "Once per cycle" steps skip themselves once done, until the next "Detect Map" step runs (i.e. a
; new round has started) resets every step's AlreadyDone flag back to false. Also resets every
; Logic step's "(Repeat)" attempt counter (see the Step Editor's "Fallback after N attempts"),
; since a new round means whatever it was retrying is a fresh situation.
ResetOncePerCycleFlags() {
    global PresetScreens
    for scr in PresetScreens
        for st in scr.Steps {
            st.AlreadyDone := false
            st.FallbackAttemptCount := 0
        }
}

; If the Edit Preset window is currently open (and showing the preset that's actually running),
; keeps it following along with the macro - switches it to whichever screen is about to execute
; and highlights/scrolls to that step. This is a "follow" view: switching screens flushes whatever
; was shown for the previous one to ini first (so nothing typed is lost), then reloads the new
; screen fresh from ini, discarding any not-yet-saved edits made to IT in the meantime.

; Resolves which map to act on: the map detected via "Detect Map" this cycle, or the preset's
; configured Default Map if none was detected (or detection hasn't run yet). Uses the ACTUALLY
; RUNNING preset (RunningPresetName), not whatever's selected in the GUI (CurrentPresetName) - the
; Default Map is per-preset, so selecting a different preset in the list mid-run must not change
; which map the running preset falls back to.
ResolveMapName() {
    global LastDetectedMap, RunningPresetName
    mapName := LastDetectedMap
    if (mapName = "") {
        defaultMap := Cfg(GamePresetSection(RunningPresetName), "DefaultMap", "(none)")
        if (defaultMap != "" && defaultMap != "(none)") {
            mapName := defaultMap
            LogMsg("No map detected - using Default Map: " mapName ".")
        }
    }
    return mapName
}

; Runs a map's Drag/Zoom Out actions (Map Advanced Settings), then marks them done for this cycle
; so the automatic trigger inside "Place Towers" doesn't repeat them - whichever of "Place Towers"
; or an explicit "Camera Setup" step runs first for this cycle "wins", the other becomes a no-op.
; Uses the map's own custom camera/zoom steps if it has them enabled, otherwise the active game's
; shared ones. With force=true the shared once-per-cycle guard is bypassed (the actions run
; every time this is called), but the flag is still set afterwards - used by the explicit "Camera
; Setup" step, whose own repetition is governed solely by that step's "Once per cycle" checkbox.
RunMapAdvStepsForMap(mapName, clickDelay, force := false) {
    global Running, MapAdvStepsDoneThisCycle
    if (MapAdvStepsDoneThisCycle && !force)
        return   ; already ran the camera/zoom actions for this cycle
    mapSection := GameMapProfileSection(mapName)
    useCustom := SafeInt(Cfg(mapSection, "CustomCamera", "0"))
    camSection := useCustom ? mapSection : GameSection()
    advSteps := GetMapAdvSteps(camSection)
    if (advSteps.Length = 0)
        return   ; no camera/zoom actions configured for this map - nothing to do
    LogMsg("Camera setup for '" mapName "' (" advSteps.Length " action(s))...")
    for advStep in advSteps {
        if !Running
            return
        if (advStep.Type = "Drag") {
            ds := AbsXY(advStep.X, advStep.Y), de := AbsXY(advStep.EndX, advStep.EndY)
            DragRightClick(ds.x, ds.y, de.x, de.y, SafeInt(advStep.DragMs))
            LogMsg("  Camera dragged (" advStep.DragMs " ms).")
        } else if (advStep.Type = "Zoom Out") {
            ZoomOutTicks(SafeInt(advStep.X))
        }
        Sleep clickDelay
    }
    MapAdvStepsDoneThisCycle := true
}

; Resolves which screen a Logic step should jump to given its OCR result: true -> OnTrueScreen,
; false -> OnFalseScreen. "(continue)" (or blank) means "don't jump, keep running this screen".
LogicJumpTarget(step, result) {
    target := result ? step.OnTrueScreen : step.OnFalseScreen
    return (target = "" || target = "(continue)") ? "" : target
}

; Tallies the session-lifetime Victory/Defeat counters (Application Stats overlay) whenever the
; text an OCR scan actually recognized on screen CONTAINS "victory" or "defeat" (case-insensitive)
; - deliberately looks at the raw recognized text rather than the step's own configured expected
; text/outcome name, since a single detection step often can't tell the two outcomes apart itself
; (e.g. one combined "Round End" check whose Label is just used to detect that the round ended at
; all, while the banner it reads happens to say "Victory" or "Defeat"). Called from the "Round
; End/Ingame/Custom Detection" case in RunSteps for every OCR scan, matched or not.
TrackVictoryDefeat(recognizedText) {
    global VictoryCount, DefeatCount
    if (recognizedText = "")
        return
    t := StrLower(recognizedText)
    if InStr(t, "victory")
        VictoryCount += 1
    else if InStr(t, "defeat")
        DefeatCount += 1
    else
        return
    RenderStatsPanel()
}

; Runs one screen's steps in order. Returns the name of the screen to jump to next (set by a
; Logic step's On True/On False result), or "" if the screen ran to the end without any jump
; firing - meaning the caller should fall through to the next screen in list order.
; startAt (1-based) lets the caller begin partway into `steps`, skipping everything before it -
; used by "Start Macro From This Step" for the very first screen it runs; every other call uses
; the default of 1 (run the whole screen from the top), same as before.
RunSteps(steps, startAt := 1) {
    global Running, Paused, LastDetectedMap, CurrentPresetName, MapAdvStepsDoneThisCycle
    global RunningScreenName
    global RunningStepDescription
    global UsageUsedEdits
    global StepRepeatCount, VictoryCount, DefeatCount, RunningPresetName
    global StepTimeMs, CurrentStepKey, StepCurrentStartTick
    clickDelay := SafeInt(Cfg(GameSection(), "ClickDelayMs", "300"))
    placeTowerDelay := SafeInt(Cfg(GameSection(), "PlaceTowerDelayMs", "100"))
    presetSection := GamePresetSection(RunningPresetName)

    ; Index-based (rather than a plain for-in) so a step whose On True/On False resolves to
    ; "(Repeat)" can redo itself by simply not advancing stepIdx, instead of moving on to the
    ; next step - see the "(Repeat)" handling near the bottom of this loop.
    stepIdx := 1
    while (stepIdx <= steps.Length) {
        step := steps[stepIdx]
        if (stepIdx < startAt) {
            stepIdx += 1
            continue
        }
        if !Running
            return ""
        while Paused {
            Sleep 200
            if !Running
                return ""
        }

        if (step.OncePerCycle && step.AlreadyDone) {
            stepIdx += 1
            continue
        }

        RunningStepDescription := step.Type . (step.Label != "" ? " (" step.Label ")" : "")
        ; Every entry here is one "attempt" at this step, including a step re-entering itself via
        ; "(Repeat)" - close out whatever attempt was previously in progress (any step, including
        ; this same one) into StepTimeMs before starting this attempt's own live timer.
        newStepKey := RunningScreenName " - " RunningStepDescription
        if (CurrentStepKey != "") {
            prevStepMs := StepTimeMs.Has(CurrentStepKey) ? StepTimeMs[CurrentStepKey] : 0
            StepTimeMs[CurrentStepKey] := prevStepMs + (Now64() - StepCurrentStartTick)
        }
        CurrentStepKey := newStepKey
        StepCurrentStartTick := Now64()
        RenderStatsPanel()
        RenderTimeBreakdownPanel()

        stepJumpTarget := ""

        switch step.Type {
            case "Start":
                ; Marker only - identifies which screen this preset's cycle starts on (see
                ; FindStartScreenIndex). No action here.

            case "Option Select":
                ; Try each option in priority order: click it, then (if an Availability Check is
                ; configured for it) verify it's actually playable right now via OCR - if not,
                ; click Back and move on to the next priority. Every option is re-checked fresh
                ; like this on every single pass (no cooldown/skip-ahead) - only "Available at
                ; start" unchecked, or its daily "Max" limit already reached, skips one without
                ; clicking it. If NONE end up available, jump straight to the Fallback Screen
                ; instead - or, if that's set to "(Stop Macro)", stop the run outright (both of
                ; which stay in effect every cycle for the rest of the day once every option's
                ; daily limit is exhausted, since none of them can become available again until
                ; the counters reset tomorrow). With no Fallback Screen configured, falls back to
                ; the old wait-5s-and-recheck loop.
                fbScreen := Cfg(presetSection, "FallbackScreen", "(none)")
                stopOnExhausted := (fbScreen = "(Stop Macro)")
                hasFallback := (!stopOnExhausted && fbScreen != "" && fbScreen != "(none)")
                usageSection := presetSection

                order := []
                Loop 3 {
                    oi := A_Index
                    order.Push({Idx: oi, Prio: SafeInt(Cfg(presetSection, "Option" oi "Priority", String(oi)), oi)})
                }
                Loop order.Length - 1 {
                    outer := A_Index
                    Loop order.Length - outer {
                        j := A_Index
                        if (order[j].Prio > order[j + 1].Prio) {
                            tmp := order[j]
                            order[j] := order[j + 1]
                            order[j + 1] := tmp
                        }
                    }
                }

                picked := false
                while (!picked && Running) {
                    for entry in order {
                        if !Cfg(presetSection, "Option" entry.Idx "Available", "1")
                            continue
                        maxUses := SafeInt(Cfg(presetSection, "Option" entry.Idx "MaxUses", "0"), 0)
                        usedToday := GetOptionUsedToday(usageSection, entry.Idx)
                        if (maxUses > 0 && usedToday >= maxUses) {
                            LogMsg("Option " entry.Idx " '" Cfg(presetSection, "Option" entry.Idx "Name", "Option " entry.Idx) "': daily limit reached (" usedToday "/" maxUses ") - skipping.")
                            continue
                        }
                        oc := AbsXY(Cfg(presetSection, "Option" entry.Idx "X", "0"), Cfg(presetSection, "Option" entry.Idx "Y", "0"))
                        ActClick(oc.x, oc.y)
                        Sleep clickDelay
                        LogMsg("Option " entry.Idx " '" Cfg(presetSection, "Option" entry.Idx "Name", "Option " entry.Idx) "': selected, checking availability...")
                        ; Read straight from presetSection, not opt.DetX/DetY/etc - those plain fields are
                        ; only refreshed by LoadPreset()/the OptionAvailGui popup, both native-GUI-only
                        ; paths tied to whatever preset happens to be BROWSED, not RunningPresetName. A user
                        ; switching the viewed preset mid-run used to make clicks land on the running
                        ; preset's option position while availability detection used a DIFFERENT preset's
                        ; region/text - reading Cfg() here keeps both halves consistent with each other.
                        detText := Cfg(presetSection, "Option" entry.Idx "DetText", "")
                        if (detText != "") {
                            da := AbsXY(Cfg(presetSection, "Option" entry.Idx "DetX", "0"), Cfg(presetSection, "Option" entry.Idx "DetY", "0"))
                            db := AbsXY(Cfg(presetSection, "Option" entry.Idx "DetEndX", "0"), Cfg(presetSection, "Option" entry.Idx "DetEndY", "0"))
                            detRect := {x: Min(da.x, db.x), y: Min(da.y, db.y), w: Abs(db.x - da.x), h: Abs(db.y - da.y)}
                            found := IsTextDetectedInRegion(detRect, detText)
                            available := SafeInt(Cfg(presetSection, "Option" entry.Idx "DetInvert", "0")) ? !found : found
                            ReactivateGameWindow()
                            if !available {
                                LogMsg("Option " entry.Idx " '" Cfg(presetSection, "Option" entry.Idx "Name", "Option " entry.Idx) "': not available -> going back.")
                                bc := AbsXY(Cfg(presetSection, "BackX", "0"), Cfg(presetSection, "BackY", "0"))
                                ActClick(bc.x, bc.y)
                                Sleep clickDelay
                                continue
                            }
                        }
                        picked := true
                        newUsed := IncrementOptionUsed(RunningPresetName, entry.Idx)
                        try UsageUsedEdits[entry.Idx].Value := newUsed
                        LogMsg("Option " entry.Idx " '" Cfg(presetSection, "Option" entry.Idx "Name", "Option " entry.Idx) "': available -> playing (" newUsed "/" (maxUses > 0 ? maxUses : "unlimited") " today).")
                        break
                    }
                    if picked
                        break
                    if stopOnExhausted {
                        LogMsg("No option available (daily limits reached) -> stopping the macro.")
                        Running := false
                        break
                    }
                    if hasFallback {
                        LogMsg("No option available -> fallback screen '" fbScreen "'.")
                        stepJumpTarget := fbScreen
                        break
                    }
                    LogMsg("No option available - rechecking in 5.00s...")
                    Sleep 5000
                }
                if !Running
                    return ""

            case "Button Click", "Press Start Button", "Restart Stage Button":
                bp := AbsXY(step.X, step.Y)
                ActClick(bp.x, bp.y, (step.Label != "" ? "'" step.Label "'" : step.Type))
                Sleep clickDelay

            case "Detect Map":
                ; Reached the map detection screen again - a new round is starting, so any
                ; "Once per cycle" steps (and the map's Drag/Zoom Out actions) are allowed to run
                ; once more.
                ResetOncePerCycleFlags()
                MapAdvStepsDoneThisCycle := false
                ; Run this step WHILE the map name banner is still visible (e.g. right after
                ; Option Select, before the button clicks that enter the round) - the banner is
                ; usually gone once you're already in-game, so detecting later won't work.
                LogMsg("Detecting map...")
                LastDetectedMap := DetectMapProfileInRegion(RectFromStep(step), 5)
                ; The OCR helper shells out to PowerShell, which can steal window focus even when
                ; hidden. Reactivate the game window so subsequent Send/Click still land correctly.
                ReactivateGameWindow()
                mapDetected := (LastDetectedMap != "")
                if !mapDetected
                    LogMsg("Map detection: no map matched (will use Default Map if one is set).")
                else
                    LogMsg("Map detected: " LastDetectedMap ".")
                RenderStatsPanel()
                stepJumpTarget := LogicJumpTarget(step, mapDetected)

            case "Camera Setup":
                ; Explicitly runs this map's Drag/Zoom Out actions (Map Advanced Settings) - put
                ; this as the first step of a screen (e.g. "Ingame") if you need the camera
                ; positioned/zoomed out BEFORE anything else happens on that screen, rather than
                ; waiting for a "Place Towers" step to trigger it implicitly. Whether it runs once
                ; per cycle or every time this step is reached is decided SOLELY by this step's own
                ; "Once per cycle" checkbox (via the OncePerCycle/AlreadyDone skip near the top of
                ; this loop) - so force=true here bypasses the shared once-per-cycle guard.
                mapName := ResolveMapName()
                if (mapName = "") {
                    LogMsg("Camera setup skipped: no map detected and no Default Map set.")
                } else {
                    ReactivateGameWindow()
                    RunMapAdvStepsForMap(mapName, clickDelay, true)
                }

            case "Place Towers":
                mapName := ResolveMapName()
                if (mapName = "") {
                    LogMsg("Tower placement skipped: no map detected and no Default Map set.")
                } else {
                    ReactivateGameWindow()
                    ; Map actions (Drag/Zoom Out) come from [General] (shared) unless this map has
                    ; its own custom copy (set via the "custom camera/zoom" checkbox on that map).
                    ; Only runs once per cycle - a no-op here if a "Camera Setup" step already ran
                    ; it earlier on this screen, or reset again once a "Detect Map" step runs.
                    RunMapAdvStepsForMap(mapName, clickDelay)
                    placements := GetMapProfilePlacements(mapName)

                    LogMsg("Placing " placements.Length " tower(s) on '" mapName "'...")
                    placedNum := 0
                    for row in placements {
                        if !Running
                            return ""
                        placedNum += 1
                        ActSend(row.Slot)
                        Sleep placeTowerDelay
                        ; Same click method as "Button Click" / "Press Start Button" / "Restart Stage Button".
                        tp := AbsXY(row.X, row.Y)
                        ActClick(tp.x, tp.y)
                        Sleep placeTowerDelay
                        LogMsg("  Tower " placedNum "/" placements.Length " placed (slot " row.Slot ").")
                        if SafeInt(Cfg(GameSection(), "AfterPlaceClick", "0")) {
                            ap := AbsXY(Cfg(GameSection(), "AfterPlaceClickX", "0"), Cfg(GameSection(), "AfterPlaceClickY", "0"))
                            ActClick(ap.x, ap.y)
                            Sleep placeTowerDelay
                        }
                    }
                }

            case "Round End Detection", "Ingame Detection", "Custom Detection":
                if (step.Type = "Custom Detection" && step.Advanced) {
                    ; Advanced Detection: N named outcomes instead of a single fixed True/False -
                    ; one OCR scan of the region, checked against every outcome's Name (exact match
                    ; across all outcomes first, then a forgiving fuzzy pass - same two-pass order
                    ; DetectMapProfileInRegion uses, so two outcomes sharing a short substring can't
                    ; get confused with each other). First match wins.
                    LogMsg("Detection '" (step.Label != "" ? step.Label : "advanced") "': scanning...")
                    rect := RectFromStep(step)
                    text := (rect.w > 0 && rect.h > 0) ? RunOcrOnRegion(rect.x, rect.y, rect.w, rect.h) : ""
                    ReactivateGameWindow()
                    outcomes := ParseOutcomes(step.OutcomesRaw)
                    matched := ""
                    if (text != "") {
                        for o in outcomes {
                            if (o.Name != "" && InStr(text, o.Name)) {
                                matched := o
                                break
                            }
                        }
                        if (matched = "") {
                            for o in outcomes {
                                if (o.Name != "" && TextContainsPartialMatch(text, o.Name, 6)) {
                                    matched := o
                                    break
                                }
                            }
                        }
                    }
                    TrackVictoryDefeat(text)
                    if (matched != "") {
                        if (matched.Screen = "(Stop Macro)") {
                            LogMsg("  -> outcome '" matched.Name "' matched -> stopping the macro.")
                            Running := false
                        } else if (matched.Screen != "" && matched.Screen != "(continue)") {
                            LogMsg("  -> outcome '" matched.Name "' matched -> screen '" matched.Screen "'.")
                            stepJumpTarget := matched.Screen
                        } else {
                            LogMsg("  -> outcome '" matched.Name "' matched -> continue.")
                        }
                    } else {
                        LogMsg("  -> no outcome matched (saw: " OcrPreview(text) ").")
                    }
                } else {
                    what := (step.Type = "Round End Detection") ? "round end" : (step.Type = "Ingame Detection") ? "ingame" : (step.Label != "" ? "'" step.Label "'" : "detection")
                    LogMsg("Checking " what "...")
                    detectResult := IsTextDetectedInRegion(RectFromStep(step), step.Label, &recognizedText)
                    ReactivateGameWindow()
                    LogMsg("  -> " (detectResult ? "detected" : "not detected") ".")
                    ; Victory/Defeat tracking looks at what the OCR actually saw on screen, not at
                    ; this step's own configured expected text - so it still works even when a
                    ; single step (like a combined "Victory Defeat" round-end check) can't itself
                    ; tell the two outcomes apart.
                    TrackVictoryDefeat(recognizedText)
                    stepJumpTarget := LogicJumpTarget(step, detectResult)
                }

            case "Drag":
                ds := AbsXY(step.X, step.Y)
                de := AbsXY(step.EndX, step.EndY)
                dDurMs := SafeInt(step.DragMs)
                DragRightClick(ds.x, ds.y, de.x, de.y, dDurMs)
                LogMsg("Dragged " (step.Label != "" ? "'" step.Label "' " : "") "(" dDurMs " ms).")

            case "Zoom Out":
                ticks := SafeInt(step.X)
                if (ticks > 0) {
                    ActWheelDown(ticks)
                    LogMsg("Zoomed out (" ticks " ticks).")
                }

            case "Wait":
                ; no action here; the "Wait After" value below performs the delay
        }

        ; Mechanic steps (everything except Detect Map / Round End Detection / Ingame Detection)
        ; have no OCR result to branch on, so their "On True" field is just an unconditional jump
        ; instead - e.g. a plain Round End button that always goes straight back to "Ingame".
        ; Skipped if stepJumpTarget is already set (e.g. "Option Select" jumping to its Fallback
        ; Screen because nothing was available) - that more specific jump takes priority.
        if (!IsLogicStepType(step.Type) && stepJumpTarget = "" && step.OnTrueScreen != "" && step.OnTrueScreen != "(continue)")
            stepJumpTarget := step.OnTrueScreen

        if step.OncePerCycle
            step.AlreadyDone := true

        extraWait := SafeNum(step.Seconds)
        if (extraWait > 0) {
            WaitSecondsInterruptible(extraWait, "Waiting ")
            LogMsg("Waited " Fmt2(extraWait) "s.")
        }

        ; Logic steps with "Fallback after N attempts" enabled: count consecutive passes that
        ; resolved to "(Repeat)" without success, and once the configured limit is reached, swap
        ; to the configured Fallback Screen (or stop the macro) instead of repeating forever.
        if (IsLogicStepType(step.Type) && step.FallbackEnabled) {
            if (stepJumpTarget = "(Repeat)") {
                step.FallbackAttemptCount += 1
                maxAttempts := Max(1, SafeInt(step.FallbackMaxAttempts, 5))
                if (step.FallbackAttemptCount >= maxAttempts) {
                    step.FallbackAttemptCount := 0
                    if (step.FallbackScreen = "(Stop Macro)") {
                        LogMsg("Fallback: no success after " maxAttempts " attempt(s) -> stopping the macro.")
                        Running := false
                        stepJumpTarget := ""
                    } else if (step.FallbackScreen != "" && step.FallbackScreen != "(none)") {
                        LogMsg("Fallback: no success after " maxAttempts " attempt(s) -> screen '" step.FallbackScreen "'.")
                        stepJumpTarget := step.FallbackScreen
                    }
                    ; else: enabled but no Fallback Screen chosen - nothing configured to switch to,
                    ; so keep repeating as before instead of silently doing nothing.
                }
            } else {
                step.FallbackAttemptCount := 0
            }
        }

        ; "(Repeat)" re-runs this exact step again - stepIdx is deliberately left unchanged - rather
        ; than being returned up to MainLoop as if it were a real screen name to jump to.
        if (stepJumpTarget = "(Repeat)") {
            StepRepeatCount += 1
            RenderStatsPanel()
            continue
        }

        if (stepJumpTarget != "" && Running)
            return stepJumpTarget

        stepIdx += 1
    }
    return ""
}

; ============================================================
; MODULES
; ============================================================
; Self-contained optional add-ons kept out of this main file. #Include splices them in textually, so
; they share the same globals/functions; each stays a no-op until explicitly enabled.
#Include remote_bridge.ahk
#Include local_bridge.ahk

