#Requires AutoHotkey v2.0
#SingleInstance Force
CoordMode "Pixel", "Screen"
CoordMode "Mouse", "Screen"
CoordMode "ToolTip", "Screen"

; Keep this in sync with the release tag (v0.3.0, v0.4.0, ...). The release workflow refuses to
; publish when the tag and this value differ, so every EXE can reliably compare itself with the
; latest GitHub release.
AppName := "Kimberlite's Anime Expedition Macro"
LegacyAppName := "Anime Expedition Macro"
AppVersion := "0.4.4"
ReleaseBaseUrl := "https://github.com/kimberlite22/Anime-Expedition-Macro-Menu/releases/latest/download/"
ReleaseExeName := "Kimberlites-Anime-Expedition-Macro.exe"
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

    try {
        FileInstall "ocr_server.exe", RuntimeDir "\ocr_server.exe", 1
    } catch as err {
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
    req.SetRequestHeader("User-Agent", "Kimberlites-Anime-Expedition-Macro/" AppVersion)
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
            "Str", "Kimberlites-Anime-Expedition-Macro/" AppVersion,
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
    script .= "  [System.Windows.MessageBox]::Show('The update could not replace the current EXE. Move it to a writable folder and try again.','Kimberlite''s Anime Expedition Macro Update') | Out-Null`r`n"
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

; Sets a DropDownList's selection to `value`, falling back to `fallback` (or, failing that too,
; leaving whatever was already selected) instead of throwing "Invalid value" - which AHK raises
; whenever the assigned text doesn't exactly match one of the control's current items. This can
; happen with perfectly valid saved data whenever the control's item list hasn't caught up yet
; (e.g. a step imported from another preset whose On True/On False points at a screen name that
; doesn't exist here) - a hard crash on stale/foreign data is worse than silently falling back.
SetDdlTextSafe(ddl, value, fallback := "(continue)") {
    try {
        ddl.Text := value
        return
    }
    try ddl.Text := fallback
}

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
    section := "Preset_" presetName
    newCount := GetOptionUsedToday(section, i) + 1
    SetOptionUsedToday(section, i, newCount)
    return newCount
}

; Refreshes the Preset Settings tab's "Today's Challenge Usage" rows for `name` - option names/max
; mirrored from OptData (already loaded by the time this is called from LoadPreset/SavePresetToIni),
; used-today counts read fresh from ini (auto-resetting on a new day, see GetOptionUsedToday).
LoadUsageFields(name) {
    global OptData, UsageNameTexts, UsageUsedEdits, UsageMaxEdits
    section := "Preset_" name
    Loop 3 {
        i := A_Index
        opt := OptData[i]
        try UsageNameTexts[i].Text := opt.NameEdit.Value
        try UsageUsedEdits[i].Value := GetOptionUsedToday(section, i)
        try UsageMaxEdits[i].Value := SafeInt(opt.MaxEdit.Value, 0)
    }
}

; True if the preset has at least one "Option Select" step in any of its screens - i.e. it's a
; challenge-style preset whose daily option usage is meaningful.
PresetUsesOptionSelect(name) {
    section := "Preset_" name
    screenCount := Integer(Cfg(section, "ScreenCount", "0"))
    Loop screenCount {
        si := A_Index
        stepCount := Integer(Cfg(section, "Screen" si "StepCount", "0"))
        Loop stepCount {
            if (Cfg(section, "Screen" si "Step" A_Index "Type", "") = "Option Select")
                return true
        }
    }
    return false
}

; Shows the "Today's Challenge Usage" group only for presets that actually use an Option Select
; step; hides it entirely for everything else (where the 3 option counters mean nothing).
UpdateUsageBoxVisibility(name) {
    global UsageBoxControls
    show := PresetUsesOptionSelect(name)
    for ctrl in UsageBoxControls
        try ctrl.Visible := show
}

; Persists a manual edit to one of the Preset Settings tab's "used today" fields immediately -
; these are daily counters, not "click Save to keep it" config, so they save on every change.
SaveUsageFieldClick(i, ctrl, *) {
    global CurrentPresetName, UsageUsedEdits
    section := "Preset_" CurrentPresetName
    SetOptionUsedToday(section, i, SafeInt(UsageUsedEdits[i].Value, 0))
}

; Persists a manual edit to one of the Preset Settings tab's daily-limit fields immediately, and
; mirrors it into OptData's MaxEdit (the same field shown in Edit Preset > Option > Max) so both
; stay in sync regardless of which one was just edited.
SaveUsageMaxFieldClick(i, ctrl, *) {
    global CurrentPresetName, ConfigFile, OptData
    val := Max(0, SafeInt(ctrl.Value, 0))
    OptData[i].MaxEdit.Value := val
    IniWrite val, ConfigFile, "Preset_" CurrentPresetName, "Option" i "MaxUses"
}

; ============================================================
; HOVER TOOLTIPS ("?" help icons)
; ============================================================
; Adds a small gray "?" icon at the given position and shows tipText as a tooltip
; while the mouse hovers over it. Returns the created Text control.
AddHelpIcon(guiObj, x, y, tipText) {
    global HoverTooltipMap
    icon := guiObj.AddText("x" x " y" y " w16 h16 Center Border", "?")
    icon.SetFont("s8 cGray Bold")
    HoverTooltipMap[icon.Hwnd] := tipText
    return icon
}

CheckHoverTooltips() {
    global HoverTooltipMap, LastHoverHwnd
    MouseGetPos(&mx, &my, , &ctrlHwnd, 2)
    if HoverTooltipMap.Has(ctrlHwnd) {
        if (ctrlHwnd != LastHoverHwnd) {
            ToolTip(HoverTooltipMap[ctrlHwnd], mx + 16, my + 16)
            LastHoverHwnd := ctrlHwnd
        }
    } else if (LastHoverHwnd != 0) {
        ToolTip()
        LastHoverHwnd := 0
    }
}
SetTimer(CheckHoverTooltips, 100)

; ============================================================
; GLOBAL STATE
; ============================================================
Running := false
Paused := false
DryRun := false          ; "test mode": walk the preset and LOG every action, but skip the actual
                          ; clicks/keypresses/drags - for safely watching what a preset WOULD do.
                          ; Read from dryRunChk at StartMacro time; not persisted (always off on launch).
RegionPreviewGui := ""   ; translucent overlay that briefly highlights an OCR region on screen
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
OverlayGuis := []          ; the 4 gray overlay bar windows
OverlayVisible := false
LockedProcess := ""        ; exe name of the window currently locked into the opening
MarkerGui := ""             ; red dot marker shown during position capture
LastDetectedMap := ""       ; map name found by the most recent "Detect Map" step (map banner is often
                             ; only visible on the selection screen, not once you're already in the round)
LogGui := ""                 ; log panel window shown in the gray area right of the game window
LogEdit := ""                 ; the read-only multi-line Edit control inside LogGui
LogLines := []                ; recent log lines (capped), mirrored into LogEdit when it exists
ScreenCountGui := ""           ; "Screen Run Counts" panel shown below LogGui, in the same gray column
ScreenCountEdit := ""          ; the read-only multi-line Edit control inside ScreenCountGui
ScreenRunCounts := Map()       ; screen name -> how many times it's been run so far THIS run - resets
                               ; every MainLoop() call, same scope as ScreenRepeatCount/StepRepeatCount
StatsGui := ""                ; "Application Stats" panel shown below LogGui in the same gray area
StatsCycleText := ""           ; text controls inside StatsGui, one per stat row (see RenderStatsPanel)
StatsMapText := ""
StatsScreenText := ""
StatsStepText := ""
StatsStepRepeatText := ""
StatsStartRepeatText := ""
StatsVictoryText := ""
StatsDefeatText := ""
StatsLastVals := Map()        ; last value pushed to each stats control (keyed by field) - lets
                               ; RenderStatsPanel (called every step) skip control updates whose value
                               ; didn't actually change, avoiding needless WM_SETTEXT/repaint churn
ScreenRepeatCount := 0        ; screen-repetitions (returns to the Start screen) so far THIS run -
                               ; resets every MainLoop() call; was called "Cycle Count"
StepRepeatCount := 0          ; how many times any step's On True/On False resolved to "(Repeat)"
                               ; so far THIS run - resets every MainLoop() call, same scope as ScreenRepeatCount
StartRepeatCount := 0         ; lifetime count of screen-repetitions across the whole session (does NOT
                               ; reset on restart/auto-reconnect) - same event as ScreenRepeatCount, just
                               ; never reset, so it keeps counting across auto-reconnect restarts
VictoryCount := 0             ; lifetime count of OCR scans whose RECOGNIZED text contained "Victory"
DefeatCount := 0              ; lifetime count of OCR scans whose RECOGNIZED text contained "Defeat" -
                               ; both come from any Round End/Ingame/Custom Detection step's scan
                               ; (matched or not) - see TrackVictoryDefeat()
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
OcrServerPid := 0                  ; PID of the persistent OCR helper (ocr_server.ps1) - 0 when not running.
                                   ; One long-lived process loads the .NET/WinRT OCR assemblies ONCE and then
                                   ; services every scan, instead of paying ~0.5s of powershell.exe startup per
                                   ; call (see EnsureOcrServer/RunOcrOnRegion).
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

; ============================================================
; BUILD GUI
; ============================================================
MyGui := Gui("+Resize", AppName " v" AppVersion)
MyGui.SetFont("s10")

tab := MyGui.AddTab3("x10 y10 w800 h700", ["Preset Settings", "Map Placement", "General"])

; ---------------- TAB 1: PRESET SETTINGS (options + preset selector) ----------------
tab.UseTab(1)

; --- preset list (scrollable) + management ---
MyGui.AddText("x30 y65", "Presets:")
AddHelpIcon(MyGui, 90, 63, "Presets are step sequences (e.g. 'Challenges'). Select one below to view/edit it. Which preset actually RUNS on Start is set separately with 'Set as Active' - see the green 'Runs on Start' line at the bottom.")
presetListBox := MyGui.AddListBox("x30 y85 w300 h100 VScroll")
presetListBox.OnEvent("Change", (*) => PresetListChanged())

MyGui.AddButton("x340 y85 w130", "New").OnEvent("Click", (*) => NewPresetClick())
MyGui.AddButton("x340 y117 w130", "Rename").OnEvent("Click", (*) => RenamePresetClick())
MyGui.AddButton("x340 y149 w130", "Delete").OnEvent("Click", (*) => DeletePresetClick())
MyGui.AddButton("x340 y181 w130", "Edit").OnEvent("Click", (*) => OpenEditGui())

MyGui.AddButton("x480 y85 w130", "Export...").OnEvent("Click", (*) => ExportPresetClick())
MyGui.AddButton("x480 y117 w130", "Import...").OnEvent("Click", (*) => ImportPresetFileClick())
setActiveBtn := MyGui.AddButton("x480 y149 w130", "Set as Active ▶")
setActiveBtn.OnEvent("Click", (*) => SetActivePresetClick())
AddHelpIcon(MyGui, 615, 151, "Makes the currently-selected preset the ACTIVE one - the preset that runs when you press Start (F10). This is separate from just selecting a preset in the list to view/edit it, so you can browse or tweak other presets without changing what will actually run. The active preset is shown in green on the 'Runs on Start' line at the bottom.")
AddHelpIcon(MyGui, 615, 87, "Export saves the selected preset - all its screens, steps, options and settings - to a .ini file you can back up or share. Import loads such a file back as a new preset. Coordinates are stored window-relative (percent), so a shared preset works even on a different screen position/resolution. Map profiles aren't bundled - set the Default Map after importing if the preset uses one.")

; --- today's usage per challenge option: how many times each option has already been played
; today, against its daily limit. Both numbers are directly editable here (as well as the limit
; being editable in Edit Preset > Option > Max - the two stay in sync either way). Usage auto-
; increments as the macro plays an option and auto-resets on a new day; both fields can be
; corrected by hand at any time (e.g. if some runs happened outside the macro, or to change the
; limit without opening Edit Preset). ---
; The whole group is only shown for presets that actually use an "Option Select" step (see
; UpdateUsageBoxVisibility) - every control created here is collected in UsageBoxControls so it can
; be shown/hidden as one.
UsageBoxControls.Push(MyGui.AddGroupBox("x30 y225 w470 h150", "Today's Challenge Usage"))
Loop 3 {
    i := A_Index
    rowY := 255 + (i - 1) * 35
    nameTxt := MyGui.AddText("x50 y" (rowY + 4) " w130", "Option " i)
    UsageNameTexts.Push(nameTxt)
    UsageBoxControls.Push(nameTxt)
    usedEdit := MyGui.AddEdit("x190 y" rowY " w45", "0")
    usedEdit.OnEvent("Change", SaveUsageFieldClick.Bind(i))
    UsageUsedEdits.Push(usedEdit)
    UsageBoxControls.Push(usedEdit)
    UsageBoxControls.Push(MyGui.AddText("x240 y" (rowY + 4) " w12", "/"))
    maxEdit2 := MyGui.AddEdit("x255 y" rowY " w45", "0")
    maxEdit2.OnEvent("Change", SaveUsageMaxFieldClick.Bind(i))
    UsageMaxEdits.Push(maxEdit2)
    UsageBoxControls.Push(maxEdit2)
    UsageBoxControls.Push(MyGui.AddText("x310 y" (rowY + 4) " w170", "today (0 = unlimited)"))
}
UsageBoxControls.Push(AddHelpIcon(MyGui, 458, 233, "How many times each challenge option has already been played today, against its daily limit. Both numbers are directly editable here (the daily limit is also editable in 'Edit' > Option > Max - either one stays in sync with the other). 'Used' counts up automatically as the macro runs and resets automatically every day."))

; ---------------- TAB 2: PLACEMENT ----------------
tab.UseTab(2)
MyGui.AddText("x30 y50", "Map Profile:")
mapProfileDdl := MyGui.AddDropDownList("x110 y47 w180")
MyGui.AddButton("x300 y46 w70", "New").OnEvent("Click", (*) => NewMapProfileClick())
MyGui.AddButton("x375 y46 w70", "Rename").OnEvent("Click", (*) => RenameMapProfileClick())
MyGui.AddButton("x450 y46 w70", "Delete").OnEvent("Click", (*) => DeleteMapProfileClick())

MyGui.AddText("x30 y82", "Expected Map Text:")
mapExpectedTextEdit := MyGui.AddEdit("x160 y79 w300", "")
AddHelpIcon(MyGui, 465, 79, "The map name is read via OCR from the Map Text Region (set in the Detection (OCR) tab) and matched against this text.")

mapCustomTowersChk := MyGui.AddCheckBox("x30 y148 w260", "Use custom tower slots for this map")
customSlotLabels := []
customSlotDdls := []
Loop 10 {
    i := A_Index
    xBase := 300 + (i - 1) * 45
    lbl := MyGui.AddText("x" xBase " y148 w40 Center", i)
    ddl := MyGui.AddDropDownList("x" xBase " y165 w40", ["1","2","3","4","5","6"])
    ddl.Text := "1"
    customSlotLabels.Push(lbl)
    customSlotDdls.Push(ddl)
}

; Only shown/used while "Use custom tower slots for this map" is checked - lets this map place a
; different NUMBER of towers than the shared default (General tab), not just different slots.
mapNumPlaceLbl := MyGui.AddText("x30 y198", "Number of placements for this map:")
mapNumPlaceDdl := MyGui.AddDropDownList("x260 y195 w60", ["1","2","3","4","5","6","7","8","9","10"])
mapNumPlaceDdl.Text := "4"
mapNumPlaceDdl.OnEvent("Change", (*) => UpdatePlacementVisibility())

AddHelpIcon(MyGui, 30, 172, "When unchecked, this map uses the shared default slot sequence AND placement count from the General tab. When checked, you can also override how many placements this map uses (below), independent of the shared default.")

MyGui.AddText("x30 y225", "Coordinates for this map's tower placements:")

placeYStart := 250
placeRowHeight := 30
Loop 10 {
    i := A_Index
    yBase := placeYStart + (i - 1) * placeRowHeight

    lbl := MyGui.AddText("x30 y" (yBase + 4) " w80", "Position " i ":")
    xLbl := MyGui.AddText("x200 y" (yBase + 4), "X:")
    xEdit := MyGui.AddEdit("x225 y" yBase " w60", Cfg("Placement" i, "X", "0"))
    yLbl := MyGui.AddText("x300 y" (yBase + 4), "Y:")
    yEdit := MyGui.AddEdit("x325 y" yBase " w60", Cfg("Placement" i, "Y", "0"))
    posBtn := MyGui.AddButton("x400 y" (yBase - 1) " w110", "Set Position")
    posBtn.OnEvent("Click", StartCapture.Bind(xEdit, yEdit))

    PlaceData.Push({Label: lbl, XLbl: xLbl, XEdit: xEdit, YLbl: yLbl, YEdit: yEdit, PosBtn: posBtn,
        CustomSlotDdl: customSlotDdls[i], CustomSlotLabel: customSlotLabels[i]})
}
mapCustomTowersChk.OnEvent("Click", (*) => UpdatePlacementVisibility())

; --- camera drag / zoom out actions for this map now live entirely in Advanced Settings as a
; step list (Drag / Zoom Out), since there can be zero, one, or several of them ---
MyGui.AddButton("x30 y665 w160", "Advanced Settings...").OnEvent("Click", (*) => OpenMapAdvancedGui())

; ---------------- TAB 3: TIMING ----------------
tab.UseTab(3)
MyGui.AddGroupBox("x30 y50 w750 h180", "Timing")
MyGui.AddText("x50 y115", "Extra wait after each full cycle (sec):")
roundWaitEdit := MyGui.AddEdit("x300 y112 w60", Cfg("General", "RoundWaitSeconds", "0"))

MyGui.AddText("x50 y150", "Click delay (ms):")
clickDelayEdit := MyGui.AddEdit("x300 y147 w60", Cfg("General", "ClickDelayMs", "300"))

MyGui.AddText("x420 y150", "Tower placement delay (ms):")
placeTowerDelayEdit := MyGui.AddEdit("x620 y147 w60", Cfg("General", "PlaceTowerDelayMs", "100"))
AddHelpIcon(MyGui, 690, 147, "Wait time (ms) between each action while placing a tower (hotkey -> cursor to position -> click) and between placing one tower and the next.")

MyGui.AddText("x50 y185", "Max cycles (0 = unlimited):")
maxRoundsEdit := MyGui.AddEdit("x300 y182 w60", Cfg("General", "MaxRounds", "0"))

MyGui.AddText("x50 y210", "Position marker size (px):")
markerSizeEdit := MyGui.AddEdit("x300 y207 w60", Cfg("General", "MarkerSize", "4"))

MyGui.AddGroupBox("x30 y240 w750 h145", "Tower Loadout (default slots for all maps)")
MyGui.AddText("x50 y265", "Number of placements:")
numPlaceDdl := MyGui.AddDropDownList("x260 y262 w60", ["1","2","3","4","5","6","7","8","9","10"])
numPlaceDdl.Text := "4"

MyGui.AddText("x50 y302", "Default slots (position 1 -> 10):")
Loop 10 {
    i := A_Index
    xBase := 260 + (i - 1) * 45
    ddl := MyGui.AddDropDownList("x" xBase " y299 w40", ["1","2","3","4","5","6"])
    ddl.Text := "1"
    GeneralSlotDdls.Push(ddl)
}

afterPlaceClickChk := MyGui.AddCheckBox("x50 y340 w230", "Click after each tower placed")
afterPlaceClickChk.Value := Integer(Cfg("General", "AfterPlaceClick", "0"))
MyGui.AddText("x290 y340", "X:")
afterPlaceXEdit := MyGui.AddEdit("x310 y337 w60", Cfg("General", "AfterPlaceClickX", "0"))
MyGui.AddText("x385 y340", "Y:")
afterPlaceYEdit := MyGui.AddEdit("x405 y337 w60", Cfg("General", "AfterPlaceClickY", "0"))
afterPlacePosBtn := MyGui.AddButton("x480 y336 w110", "Set Position")
afterPlacePosBtn.OnEvent("Click", StartCapture.Bind(afterPlaceXEdit, afterPlaceYEdit))
AddHelpIcon(MyGui, 600, 337, "After every single tower is placed, an extra click is made at this fixed position (e.g. to dismiss a popup or confirm placement) before moving on to the next tower.")

MyGui.AddGroupBox("x30 y395 w750 h140", "Game Window")
MyGui.AddText("x50 y420", "Process:")
gameProcessDdl := MyGui.AddDropDownList("x120 y417 w400")
MyGui.AddButton("x530 y416 w90", "Refresh").OnEvent("Click", (*) => RefreshProcessList())

MyGui.AddText("x50 y455", "Opening offset (x, y):")
holeXEdit := MyGui.AddEdit("x220 y452 w60", Cfg("General", "HoleX", "50"))
holeYEdit := MyGui.AddEdit("x285 y452 w60", Cfg("General", "HoleY", "50"))

MyGui.AddText("x50 y490", "Opening size (w, h):")
holeWEdit := MyGui.AddEdit("x220 y487 w60", Cfg("General", "HoleW", "1248"))
holeHEdit := MyGui.AddEdit("x285 y487 w60", Cfg("General", "HoleH", "702"))
AddHelpIcon(MyGui, 360, 487, "A gray fullscreen overlay opens with this rectangular opening cut out; the game window is moved into it.")

MyGui.AddGroupBox("x30 y545 w750 h165", "Disconnect Detection (Auto-Reconnect)")
disconnectEnabledChk := MyGui.AddCheckBox("x50 y570 w500", "Enable: auto-click Reconnect and restart the macro on disconnect")
disconnectEnabledChk.Value := Integer(Cfg("General", "DisconnectEnabled", "0"))
AddHelpIcon(MyGui, 758, 547, "Periodically scans the region below for the given text (e.g. a 'Reconnect' popup). When found, clicks the Reconnect Button position and restarts the currently selected preset from the beginning - as if F10 had been pressed again.")

MyGui.AddText("x50 y600", "Region1 X:")
disconnectX1Edit := MyGui.AddEdit("x125 y597 w55", Cfg("General", "DisconnectX1", "0"))
MyGui.AddText("x190 y600", "Y:")
disconnectY1Edit := MyGui.AddEdit("x210 y597 w55", Cfg("General", "DisconnectY1", "0"))
disconnectPos1Btn := MyGui.AddButton("x275 y596 w100", "Select Region")
disconnectPos1Btn.OnEvent("Click", (*) => StartRegionCapture(disconnectX1Edit, disconnectY1Edit, disconnectX2Edit, disconnectY2Edit))
MyGui.AddText("x480 y600", "Expected Text:")
disconnectTextEdit := MyGui.AddEdit("x570 y597 w190", Cfg("General", "DisconnectText", ""))

MyGui.AddText("x50 y630", "Region2 X:")
disconnectX2Edit := MyGui.AddEdit("x125 y627 w55", Cfg("General", "DisconnectX2", "0"))
MyGui.AddText("x190 y630", "Y:")
disconnectY2Edit := MyGui.AddEdit("x210 y627 w55", Cfg("General", "DisconnectY2", "0"))

MyGui.AddText("x50 y660", "Reconnect X:")
disconnectReconnectXEdit := MyGui.AddEdit("x135 y657 w55", Cfg("General", "DisconnectReconnectX", "0"))
MyGui.AddText("x200 y660", "Y:")
disconnectReconnectYEdit := MyGui.AddEdit("x220 y657 w55", Cfg("General", "DisconnectReconnectY", "0"))
disconnectReconnectPosBtn := MyGui.AddButton("x285 y656 w100", "Set Position")
disconnectReconnectPosBtn.OnEvent("Click", StartCapture.Bind(disconnectReconnectXEdit, disconnectReconnectYEdit))
MyGui.AddText("x480 y660", "Check every (sec):")
disconnectIntervalEdit := MyGui.AddEdit("x610 y657 w50", Cfg("General", "DisconnectIntervalSec", "5"))

disconnectTestBtn := MyGui.AddButton("x50 y689 w100", "Test OCR")
disconnectTestBtn.OnEvent("Click", (*) => DisconnectTestOcrClick())
disconnectShowRegionBtn := MyGui.AddButton("x160 y689 w100", "Show Region")
disconnectShowRegionBtn.OnEvent("Click", (*) => ShowRegionPreviewFromPct(disconnectX1Edit.Value, disconnectY1Edit.Value, disconnectX2Edit.Value, disconnectY2Edit.Value))
disconnectOcrResultText := MyGui.AddEdit("x270 y691 w490 h22 ReadOnly -WantReturn -E0x200", "OCR result will appear here.")

tab.UseTab()

; ---------------- STATUS & CONTROLS (always visible) ----------------
; The preset that actually runs when you press Start/F10 - chosen with "Set as Active" (Preset
; Settings tab), independent of whichever preset is currently selected for viewing/editing. (The
; old one-line status/log mirror used to sit here; the full run log now lives in the log panel.)
activePresetText := MyGui.AddText("x10 y725 w800 h20", "Runs on Start: -")
activePresetText.SetFont("s10 Bold cGreen")

dryRunChk := MyGui.AddCheckBox("x10 y778 w220", "Dry Run (test: log only, no clicks)")
AddHelpIcon(MyGui, 232, 778, "When checked and you press Start, the macro walks through the preset and LOGS every action (click/tower/detection/jump) exactly as normal, but performs NO actual clicks, key presses or drags - so you can safely watch what a preset WOULD do. Every log line is prefixed [DRY]. Uncheck for a real run. Always starts off when the app launches.")

; Master on/off for the remote bridge (remote_bridge.ahk). Placed here in the always-visible strip
; because Tab 3 (General) is full; it is the live source of truth (read every tick) and is persisted
; to [General] RemoteBridgeEnabled by SaveConfig, mirroring the Disconnect Detection enable checkbox.
remoteBridgeChk := MyGui.AddCheckBox("x260 y778 w180", "Enable remote bridge")
remoteBridgeChk.Value := Integer(Cfg("General", "RemoteBridgeEnabled", "0"))
AddHelpIcon(MyGui, 444, 778, "Lets a separate companion app on THIS PC read the macro's status and log and issue a small, fixed set of safe commands (pause, resume, stop, select/queue preset) through files in the app's local data folder. Off by default. The macro itself never opens a network connection - enabling this only creates those local files.")

saveBtn := MyGui.AddButton("x500 y775 w90", "Save")
placementBtn := MyGui.AddButton("x600 y775 w120", "Placement Mode")
startBtn := MyGui.AddButton("x730 y775 w90", "Start")
saveBtn.OnEvent("Click", (*) => (SaveConfig(), LogMsg("Configuration saved.")))
placementBtn.OnEvent("Click", (*) => PlacementModeClick())
startBtn.OnEvent("Click", (*) => StartMacroWithLocalFeedback())

; Opens the "Remote Agent Setup" popup: pairs this PC with a remote-control account and starts/stops
; the companion agent (remote/agent) directly from the GUI - logging in (or registering) with the
; account's email/password is the only manual step, no command line needed (see OpenRemoteAgentGui
; below).
remoteAgentSetupBtn := MyGui.AddButton("x10 y808 w190", "Remote Agent Setup...")
remoteAgentSetupBtn.OnEvent("Click", (*) => OpenRemoteAgentGui())
AddHelpIcon(MyGui, 205, 810, "Pair this PC with your Anime Expedition remote-control account and start/stop the background agent (remote/agent) - entirely from this app. Enable 'remote bridge' above as well so the agent has status/logs to report.")

MyGui.OnEvent("Close", (*) => (SaveConfig(), StopOcrServer(), ExitApp()))
MyGui.OnEvent("Size", (*) => "")  ; prevents errors on resize
; Also stop the OCR helper on any other exit path (e.g. Reload, tray Exit) so no orphan process
; lingers - OnExit fires for those cases the GUI Close handler above doesn't cover.
OnExit((*) => (StopOcrServer(), 0))

UpdatePlacementVisibility()
UpdateGeneralSlotVisibility()
numPlaceDdl.OnEvent("Change", (*) => (UpdatePlacementVisibility(), UpdateGeneralSlotVisibility()))

RefreshProcessList()

; ============================================================
; EDIT PRESET WINDOW (opened via the "Edit" button)
; ============================================================
; +Resize adds a resizable border AND a maximize button to the title bar, so this window can be
; dragged bigger or maximized when it feels cramped - see EditGuiSizeHandler below, which widens
; the step list to actually use the extra space instead of just leaving it blank.
; +0x200000 is the raw WS_VSCROLL window style (AHK has no named "VScroll" Gui option) - it makes
; this window show a vertical scrollbar when it's opened shorter than its full content height (see
; OpenEditGui, which caps the shown height to the screen's work area). Windows draws the scrollbar
; for a WS_VSCROLL window automatically, but does NOT move any controls or track a position on its
; own - that's hooked up by hand further below (UpdateEditGuiScrollRange/ScrollEditGuiTo/
; EditGuiOnVScroll/EditGuiOnMouseWheel).
EditGui := Gui("+Owner" MyGui.Hwnd " +Resize +MinSize860x400 +0x200000", "Edit Preset")
EditGui.SetFont("s10")
EditGui.OnEvent("Size", EditGuiSizeHandler)

editingLabel := EditGui.AddText("x20 y15 w550", "Editing: Challenges")

; --- import from another preset: either a whole screen (its full step list), or just a single
; step/component (with all its settings) picked from that screen. Handy for reusing e.g. a "Round
; End" screen, or just one popup-handling step, across multiple presets instead of rebuilding it
; by hand. ---
EditGui.AddGroupBox("x590 y5 w250 h160", "Import From Preset")
EditGui.AddText("x605 y28", "Preset:")
importPresetDdl := EditGui.AddDropDownList("x665 y25 w165")
importPresetDdl.OnEvent("Change", (*) => ImportPresetChanged())
EditGui.AddText("x605 y58", "Screen:")
importScreenDdl := EditGui.AddDropDownList("x665 y55 w165")
importScreenDdl.OnEvent("Change", (*) => ImportScreenChanged())
EditGui.AddText("x605 y88", "Component:")
importStepDdl := EditGui.AddDropDownList("x665 y85 w165")
importScreenBtn := EditGui.AddButton("x600 y120 w110 h28", "Import Screen")
importScreenBtn.OnEvent("Click", (*) => ImportScreenClick())
importStepBtn := EditGui.AddButton("x718 y120 w112 h28", "Import Step")
importStepBtn.OnEvent("Click", (*) => ImportStepClick())
AddHelpIcon(EditGui, 815, 7, "Pick a preset (and one of its screens) to import from - including the current preset itself, to duplicate one of its own screens/steps. 'Import Screen' imports the WHOLE screen's step list - either overwriting the screen currently open below (keeping its name) or added as a new screen. 'Import Step' instead adds just the single component picked below to the end of the screen currently open here, settings and all. Any 'On True/On False' jumps that point to screen names which don't exist in this preset will just fall through with a warning at runtime - rename them here afterward if needed.")

; --- screens: a preset is now a set of named screens, each with its own step list. Logic steps
; (Detect Map / Round End Detection / Ingame Detection) inside a screen can jump to any other
; screen on true/false; a screen that finishes without jumping falls through to the next screen
; in this list (wrapping back to the first after the last). ---
EditGui.AddText("x20 y45", "Screen:")
screenDdl := EditGui.AddDropDownList("x70 y42 w250")
screenDdl.OnEvent("Change", (*) => ScreenChanged())
AddHelpIcon(EditGui, 328, 44, "A screen is a named group of steps. When a screen finishes without a Logic step jumping elsewhere, execution falls through to the next screen in this list (wrapping back to the start after the last). By default the first screen is where each cycle starts and wraps back to - add a 'Start' component to any step list instead if you want a different screen to be the actual starting point.")

EditGui.AddButton("x20 y75 w95", "New Screen").OnEvent("Click", (*) => NewScreenClick())
EditGui.AddButton("x120 y75 w95", "Rename").OnEvent("Click", (*) => RenameScreenClick())
EditGui.AddButton("x220 y75 w95", "Delete").OnEvent("Click", (*) => DeleteScreenClick())
EditGui.AddButton("x320 y75 w95", "Move Up").OnEvent("Click", (*) => MoveScreenUpClick())
EditGui.AddButton("x420 y75 w95", "Move Down").OnEvent("Click", (*) => MoveScreenDownClick())

stepsLV := EditGui.AddListView("x20 y170 w750 h190 Grid", ["#", "Type", "Name", "X / Duration", "Y", "End X", "End Y", "Drag (ms)", "Once/Cycle", "On True", "On False", "Wait After (s)", "FB After N", "FB Max", "FB Screen", "Advanced", "Outcomes"])
stepsLV.ModifyCol(1, 28)
stepsLV.ModifyCol(2, 100)
stepsLV.ModifyCol(3, 95)
stepsLV.ModifyCol(4, 62)
stepsLV.ModifyCol(5, 52)
stepsLV.ModifyCol(6, 52)
stepsLV.ModifyCol(7, 52)
stepsLV.ModifyCol(8, 55)
stepsLV.ModifyCol(9, 62)
stepsLV.ModifyCol(10, 75)
stepsLV.ModifyCol(11, 75)
stepsLV.ModifyCol(12, 80)
stepsLV.ModifyCol(13, 62)
stepsLV.ModifyCol(14, 50)
stepsLV.ModifyCol(15, 75)
stepsLV.ModifyCol(16, 60)
stepsLV.ModifyCol(17, 150)
stepsLV.OnEvent("Click", (*) => LoadEditorFromSelection())
stepsLV.OnNotify(-109, StepsLVBeginDrag)   ; LVN_BEGINDRAG (LVN_FIRST-9) - drag a row to reorder the step list

EditGui.AddGroupBox("x20 y370 w750 h260", "Step Editor")
EditGui.AddText("x40 y395", "Type:")
stepTypeDdl := EditGui.AddDropDownList("x90 y392 w170", ["Start", "Option Select", "Button Click", "Press Start Button", "Restart Stage Button", "Camera Setup", "Place Towers", "Drag", "Zoom Out", "Wait", "Detect Map", "Round End Detection", "Ingame Detection", "Custom Detection"])
stepTypeDdl.Text := "Button Click"
stepLabelLbl := EditGui.AddText("x280 y395", "Name:")
stepLabelEdit := EditGui.AddEdit("x330 y392 w150", "")

; --- "Custom Detection" only: turns the single fixed True/False branch into any number of named
; outcomes, each checked (in order) against this step's OCR region - see the Advanced Detection
; Outcomes popup below. Reuses the same horizontal space Label/On True/On False would otherwise
; occupy, since those become irrelevant once outcomes take over. ---
stepAdvancedChk := EditGui.AddCheckBox("x480 y397 w140", "Advanced Detection")
stepAdvancedChk.OnEvent("Click", (*) => StepAdvancedChkToggled())
AddHelpIcon(EditGui, 624, 397, "Only for 'Custom Detection' steps. When checked, this step's single fixed True/False branch is replaced by any number of named outcomes (Configure Outcomes...) - each outcome's Name doubles as OCR expected text to match against this step's region, checked top-to-bottom, first match wins. By default there are 2 outcomes ('True'/'False', both left on '(continue)') mirroring the normal behavior, but you can rename them (which also changes what text they match) and add as many more as you need, each jumping to a different screen depending on what's detected.")
stepAdvancedConfigBtn := EditGui.AddButton("x650 y392 w120", "Configure Outcomes...")
stepAdvancedConfigBtn.OnEvent("Click", (*) => OpenAdvDetGui())

stepXLabel := EditGui.AddText("x40 y430", "X:")
stepXEdit := EditGui.AddEdit("x95 y427 w60", "0")
stepYLabel := EditGui.AddText("x170 y430", "Y:")
stepYEdit := EditGui.AddEdit("x225 y427 w60", "0")
stepPosBtn := EditGui.AddButton("x300 y426 w110", "Set Position")
stepPosBtn.OnEvent("Click", (*) => StepPosBtnClick())
EditGui.AddText("x430 y430", "Wait After (s):")
stepSecEdit := EditGui.AddEdit("x530 y427 w60", "0")

; --- Drag's end point + duration, OR a Logic step's second region corner (relabeled dynamically) ---
dragEndXLabel := EditGui.AddText("x40 y465", "End X:")
dragEndXEdit := EditGui.AddEdit("x95 y462 w60", "0")
dragEndYLabel := EditGui.AddText("x170 y465", "End Y:")
dragEndYEdit := EditGui.AddEdit("x225 y462 w60", "0")
dragEndPosBtn := EditGui.AddButton("x300 y461 w110", "Set Position")
dragEndPosBtn.OnEvent("Click", StartCapture.Bind(dragEndXEdit, dragEndYEdit))
dragMsLabel := EditGui.AddText("x430 y465", "Drag (ms):")
dragMsEdit := EditGui.AddEdit("x520 y462 w60", "500")

; --- Logic steps only: test OCR against the region/text entered above ---
stepOcrTestBtn := EditGui.AddButton("x40 y500 w110", "Test OCR")
stepOcrTestBtn.OnEvent("Click", (*) => StepTestOcrClick())
stepShowRegionBtn := EditGui.AddButton("x160 y500 w110", "Show Region")
stepShowRegionBtn.OnEvent("Click", (*) => ShowRegionPreviewFromPct(stepXEdit.Value, stepYEdit.Value, dragEndXEdit.Value, dragEndYEdit.Value))
stepOcrResultText := EditGui.AddEdit("x280 y502 w470 h22 ReadOnly -WantReturn -E0x200", "OCR result will appear here.")

; --- Where to jump when this step finishes: Logic steps get two branches (true/false, based on
; the OCR result); Mechanic steps get a single unconditional jump (reuses the same "On True"
; field/column - e.g. a plain Round End button that just always goes back to "Ingame" with no
; detection needed). ---
stepOnTrueLbl := EditGui.AddText("x40 y538", "On True ->")
stepOnTrueDdl := EditGui.AddDropDownList("x120 y535 w190")
stepOnFalseLbl := EditGui.AddText("x330 y538", "On False ->")
stepOnFalseDdl := EditGui.AddDropDownList("x415 y535 w190")
AddHelpIcon(EditGui, 615, 537, "Jump to another screen when this step finishes. Logic steps (Detect Map, Round End/Ingame/Custom Detection) can jump differently depending on whether the OCR text matched. Other steps just jump unconditionally using the 'On True' field - leave it on '(continue)' to keep running the rest of this screen normally. Pick '(Repeat)' to re-run this exact step again instead - waits for this step's own 'Wait After (s)' between attempts, so e.g. a detection step can keep rechecking itself until it matches.")

; --- once-per-cycle flag, applies to every step type ---
oncePerCycleChk := EditGui.AddCheckBox("x40 y570 w650", "Once per cycle (run only once, skip until the next Detect Map / new round)")
AddHelpIcon(EditGui, 700, 571, "When checked, this step only runs once and is then skipped on every repeat - until a 'Detect Map' step runs again (i.e. a new round starts). Useful for e.g. a Drag or Zoom Out step inside a repeating screen that shouldn't run every loop.")

; --- Logic steps only: gives up after N attempts that led to no progress (i.e. resolved to
; "(Repeat)") and jumps to a fallback screen instead - a safety net for a detection step whose
; On True/On False is set to "(Repeat)", so it doesn't loop forever if the expected text never
; shows up. ---
stepFallbackChk := EditGui.AddCheckBox("x40 y600 w195", "Fallback after N attempts:")
stepFallbackMaxEdit := EditGui.AddEdit("x235 y597 w45", "5")
stepFallbackScreenLbl := EditGui.AddText("x295 y600", "-> Screen:")
stepFallbackScreenDdl := EditGui.AddDropDownList("x365 y597 w190")
AddHelpIcon(EditGui, 615, 600, "Only for Logic steps (Detect Map, Round End/Ingame/Custom Detection). Counts how many times in a row this step's result led to '(Repeat)' (see On True/On False above) without success; once the count reaches N, it jumps to the screen picked here instead (or 'Stop Macro') - so a step retrying via '(Repeat)' can't loop forever if the expected text never appears. The count resets to 0 as soon as the step succeeds (no longer resolves to '(Repeat)'), and also whenever a new round starts (a 'Detect Map' step runs).")

EditGui.AddButton("x40 y640 w100", "Add Step").OnEvent("Click", (*) => AddStepClick())
EditGui.AddButton("x150 y640 w120", "Update Selected").OnEvent("Click", (*) => UpdateSelectedClick())
EditGui.AddButton("x280 y640 w120", "Remove Selected").OnEvent("Click", (*) => RemoveSelectedClick())
EditGui.AddButton("x410 y640 w70", "Move Up").OnEvent("Click", (*) => MoveUpClick())
EditGui.AddButton("x490 y640 w80", "Move Down").OnEvent("Click", (*) => MoveDownClick())
startFromStepBtn := EditGui.AddButton("x580 y640 w150", "Start Macro From This Step")
startFromStepBtn.OnEvent("Click", (*) => StartFromStepClick())
AddHelpIcon(EditGui, 735, 643, "Starts the macro beginning at the currently selected step, skipping everything before it on this screen. Unlike the main Start button, this runs the preset you're editing here (not the 'active' one). Later screens (via jumps/fallthrough) still run normally from their own start. While the macro runs, this window follows along - showing whichever screen/step is currently executing.")

; --- 3 challenge options, specific to this preset (only shown while editing an "Option Select" step) ---
optionSectionLabel := EditGui.AddText("x20 y680", "Challenge options for this preset (used by its 'Option Select' steps):")
OptionSectionControls.Push(optionSectionLabel)
optionBoxW := 235
optionGap := 15
optionYBase := 700
optionBoxH := 190
Loop 3 {
    i := A_Index
    xBase := 20 + (i - 1) * (optionBoxW + optionGap)

    optGroupBox := EditGui.AddGroupBox("x" xBase " y" optionYBase " w" optionBoxW " h" optionBoxH, "Option " i)

    optNameLbl := EditGui.AddText("x" (xBase + 10) " y" (optionYBase + 22), "Name:")
    nameEdit := EditGui.AddEdit("x" (xBase + 65) " y" (optionYBase + 19) " w" (optionBoxW - 75), "Option " i)

    optXLbl := EditGui.AddText("x" (xBase + 10) " y" (optionYBase + 52), "X:")
    xEdit := EditGui.AddEdit("x" (xBase + 30) " y" (optionYBase + 49) " w55", "0")
    optYLbl := EditGui.AddText("x" (xBase + 95) " y" (optionYBase + 52), "Y:")
    yEdit := EditGui.AddEdit("x" (xBase + 115) " y" (optionYBase + 49) " w55", "0")

    posBtn := EditGui.AddButton("x" (xBase + 10) " y" (optionYBase + 78) " w" (optionBoxW - 20), "Set Position")

    availChk := EditGui.AddCheckBox("x" (xBase + 10) " y" (optionYBase + 108) " w" (optionBoxW - 20), "Available at start")
    availChk.Value := 1

    optPrioLbl := EditGui.AddText("x" (xBase + 10) " y" (optionYBase + 136), "Priority:")
    prioDdl := EditGui.AddDropDownList("x" (xBase + 70) " y" (optionYBase + 133) " w60", ["1", "2", "3"])
    prioDdl.Text := String(i)

    ; Daily play limit for this option (0 = unlimited). Checked/enforced during "Option Select"
    ; (see RunSteps) and mirrored, with the actual count used today, on the Preset Settings tab.
    optMaxLbl := EditGui.AddText("x" (xBase + 140) " y" (optionYBase + 136), "Max:")
    maxEdit := EditGui.AddEdit("x" (xBase + 175) " y" (optionYBase + 133) " w45", "0")
    HoverTooltipMap[maxEdit.Hwnd] := "How many times this option may be played per day (0 = unlimited). Resets automatically every day. Once all 3 options are exhausted for today, the 'Fallback Screen' setting below takes over (including the 'Stop Macro' option)."

    ; Opens the shared Option Availability Check popup, pre-loaded for THIS option (i). Lets you
    ; configure an OCR region + expected text that verifies this option is actually playable
    ; in-game before the macro commits to it.
    availDetBtn := EditGui.AddButton("x" (xBase + 10) " y" (optionYBase + 166) " w" (optionBoxW - 20), "Availability Check...")
    availDetBtn.OnEvent("Click", OpenOptionAvailGui.Bind(i))

    posBtn.OnEvent("Click", StartCapture.Bind(xEdit, yEdit))

    OptData.Push({NameEdit: nameEdit, XEdit: xEdit, YEdit: yEdit, AvailChk: availChk, PrioDdl: prioDdl, MaxEdit: maxEdit,
        DetX: "0", DetY: "0", DetEndX: "0", DetEndY: "0", DetText: "", DetInvert: 0})
    for ctrl in [optGroupBox, optNameLbl, nameEdit, optXLbl, xEdit, optYLbl, yEdit, posBtn, availChk, optPrioLbl, prioDdl, optMaxLbl, maxEdit, availDetBtn]
        OptionSectionControls.Push(ctrl)
}

; --- Two DIFFERENT things "Option Select" needs when an option isn't available, which is why
; there are two separate controls here:
;  - Back Button: clicked to return from THAT ONE option's own details/preview screen once its
;    availability check comes back negative, so the next priority can still be tried.
;  - Fallback Screen: what to do if EVERY option turns out unavailable - jumps straight to a
;    different screen (e.g. a "Farming" screen) instead of clicking a fixed position. Leave it on
;    "(none)" to fall back to the old behavior of waiting 5s and rechecking instead. ---
EditGui.AddGroupBox("x20 y900 w800 h68", "Option Select: Back Button & Fallback Screen")
EditGui.AddText("x35 y927", "Back X:")
backXEdit := EditGui.AddEdit("x90 y924 w50", "0")
EditGui.AddText("x155 y927", "Back Y:")
backYEdit := EditGui.AddEdit("x210 y924 w50", "0")
backPosBtn := EditGui.AddButton("x280 y923 w100", "Set Position")
backPosBtn.OnEvent("Click", StartCapture.Bind(backXEdit, backYEdit))
EditGui.AddText("x410 y927", "Fallback Screen ->")
fallbackScreenDdl := EditGui.AddDropDownList("x520 y924 w250")
AddHelpIcon(EditGui, 795, 905, "Back Button: clicked to return to the mode-select screen after an option's Availability Check comes back negative, so the next priority can be tried. Fallback Screen: jumped to instead if every option turns out unavailable (including all 3 hitting their daily 'Max' limit) - leave it on '(none)' to fall back to the old behavior of waiting 5s and rechecking instead, or pick 'Stop Macro' to end the run cleanly once nothing is left to play today.")
for ctrl in [backXEdit, backYEdit, backPosBtn, fallbackScreenDdl]
    OptionSectionControls.Push(ctrl)

; --- default map fallback, specific to this preset ---
EditGui.AddText("x20 y985", "Default Map:")
defaultMapDdl := EditGui.AddDropDownList("x110 y982 w260")
AddHelpIcon(EditGui, 380, 983, "Used by 'Place Towers' if no 'Detect Map' step ran (or it found nothing) while this preset is running. Set to '(none)' to always require detection.")

EditGui.AddButton("x680 y1022 w90", "Close").OnEvent("Click", (*) => CloseEditGui())
EditGui.OnEvent("Close", (*) => CloseEditGui())

stepTypeDdl.OnEvent("Change", (*) => StepTypeChangedByUser())

; ============================================================
; EDIT PRESET WINDOW: MANUAL VERTICAL SCROLLING
; ============================================================
; EditGui's content (1070px) is taller than plenty of screens, so OpenEditGui caps its shown height
; to the work area and it's given the raw WS_VSCROLL style above. Windows draws the scrollbar for
; that style on its own, but doesn't move any controls or track a position - this section does that
; by hand: every control is repositioned by the same delta whenever the scroll offset changes,
; whether that change came from dragging/clicking the real scrollbar (WM_VSCROLL) or the mouse
; wheel (WM_MOUSEWHEEL, which the OS scrollbar does not respond to on its own).
EditGuiScrollY := 0        ; current vertical scroll offset in px (0 = top/unscrolled)
EditGuiContentHeight := 0  ; full logical content height - bottom edge of the lowest control

; Measures the content height (bottom edge of the lowest control) and (re)configures the OS
; scrollbar's range/page size to match. Called once EditGui is first shown, and again on every
; resize (the viewport height changes, so the scrollable range does too).
UpdateEditGuiScrollRange() {
    global EditGui, EditGuiScrollY, EditGuiContentHeight
    tallest := 0
    for ctrl in EditGui {
        ctrl.GetPos(&cx, &cy, &cw, &ch)
        if (cy + ch > tallest)
            tallest := cy + ch
    }
    EditGuiContentHeight := tallest + 20

    EditGui.GetClientPos(, , , &viewH)
    maxScroll := Max(0, EditGuiContentHeight - viewH)
    if (EditGuiScrollY > maxScroll)
        ScrollEditGuiTo(maxScroll)

    si := Buffer(28, 0)
    NumPut("UInt", 28, si, 0)     ; cbSize
    NumPut("UInt", 0x7, si, 4)    ; fMask: SIF_RANGE | SIF_PAGE | SIF_POS
    NumPut("Int", 0, si, 8)       ; nMin
    NumPut("Int", EditGuiContentHeight - 1, si, 12) ; nMax
    NumPut("UInt", viewH, si, 16) ; nPage
    NumPut("Int", EditGuiScrollY, si, 20) ; nPos
    DllCall("SetScrollInfo", "Ptr", EditGui.Hwnd, "Int", 1, "Ptr", si, "Int", true) ; SB_VERT = 1
}

; Moves every control by the difference between `newY` and the current scroll offset (clamped to
; the valid range), then updates the scrollbar thumb to match. Shared by the scrollbar's own
; WM_VSCROLL handler and the mouse wheel handler below.
; WM_SETREDRAW is turned off for the actual moves (avoids flicker across ~150 controls) and back
; on afterward, followed by an explicit InvalidateRect+UpdateWindow - without that last step,
; Windows never repaints the areas vacated by each moved control, leaving visible ghost trails
; behind (most noticeable scrolling down then back up).
ScrollEditGuiTo(newY) {
    global EditGui, EditGuiScrollY, EditGuiContentHeight
    EditGui.GetClientPos(, , , &viewH)
    maxScroll := Max(0, EditGuiContentHeight - viewH)
    newY := Max(0, Min(maxScroll, Round(newY)))
    delta := newY - EditGuiScrollY
    if (delta = 0)
        return
    EditGuiScrollY := newY
    DllCall("SendMessage", "Ptr", EditGui.Hwnd, "UInt", 0x0B, "Ptr", 0, "Ptr", 0) ; WM_SETREDRAW off
    for ctrl in EditGui {
        ctrl.GetPos(&cx, &cy)
        ctrl.Move(cx, cy - delta)
    }
    DllCall("SendMessage", "Ptr", EditGui.Hwnd, "UInt", 0x0B, "Ptr", 1, "Ptr", 0) ; WM_SETREDRAW on
    DllCall("SetScrollPos", "Ptr", EditGui.Hwnd, "Int", 1, "Int", newY, "Int", true)
    DllCall("InvalidateRect", "Ptr", EditGui.Hwnd, "Ptr", 0, "Int", true)
    DllCall("UpdateWindow", "Ptr", EditGui.Hwnd)
}

; WM_VSCROLL (0x115): fires when the user clicks the scrollbar's arrows/track or drags its thumb.
EditGuiOnVScroll(wParam, lParam, msg, hwnd) {
    global EditGui, EditGuiScrollY, EditGuiContentHeight
    if (hwnd != EditGui.Hwnd)
        return
    EditGui.GetClientPos(, , , &viewH)
    maxScroll := Max(0, EditGuiContentHeight - viewH)
    action := wParam & 0xFFFF
    newPos := EditGuiScrollY
    switch action {
        case 0: newPos -= 30                          ; SB_LINEUP
        case 1: newPos += 30                          ; SB_LINEDOWN
        case 2: newPos -= viewH                        ; SB_PAGEUP
        case 3: newPos += viewH                        ; SB_PAGEDOWN
        case 4, 5: newPos := (wParam >> 16) & 0xFFFF  ; SB_THUMBPOSITION / SB_THUMBTRACK
        case 6: newPos := 0                            ; SB_TOP
        case 7: newPos := maxScroll                    ; SB_BOTTOM
        default: return
    }
    ScrollEditGuiTo(newPos)
}

; WM_MOUSEWHEEL (0x20A): the OS scrollbar alone doesn't respond to the mouse wheel. Only acts when
; the cursor is directly over EditGui's own background (hwnd matches exactly, not a child control)
; so it never fights a child control's own wheel behavior (e.g. the step list's internal scrolling,
; or changing a focused dropdown's selection).
EditGuiOnMouseWheel(wParam, lParam, msg, hwnd) {
    global EditGui, EditGuiScrollY
    if (hwnd != EditGui.Hwnd)
        return
    delta := (wParam >> 16) & 0xFFFF
    if (delta > 0x7FFF)
        delta -= 0x10000
    ScrollEditGuiTo(EditGuiScrollY - Round(delta / 120) * 40)
}

OnMessage(0x115, EditGuiOnVScroll)
OnMessage(0x20A, EditGuiOnMouseWheel)

; ============================================================
; MAP ADVANCED SETTINGS WINDOW (Drag / Zoom Out action list, per map profile)
; ============================================================
MapAdvGui := Gui("+Owner" MyGui.Hwnd, "Map Advanced Settings")
MapAdvGui.SetFont("s10")

mapAdvLabel := MapAdvGui.AddText("x20 y15 w560", "Editing: shared default (all maps)")

mapCustomCameraChk := MapAdvGui.AddCheckBox("x20 y45 w580", "Use custom camera/zoom settings for this map (unchecked = use the shared default)")
mapCustomCameraChk.OnEvent("Click", OnMapCustomCameraToggled)
AddHelpIcon(MapAdvGui, 605, 46, "These actions run once (each) before towers are placed, right after the map is detected - not every time. They only repeat again after a new 'Detect Map' (i.e. a new round).")

mapAdvStepsLV := MapAdvGui.AddListView("x20 y75 w600 h150 Grid", ["#", "Type", "X / Ticks", "Y", "End X", "End Y", "Drag (ms)"])
mapAdvStepsLV.ModifyCol(1, 30)
mapAdvStepsLV.ModifyCol(2, 100)
mapAdvStepsLV.ModifyCol(3, 80)
mapAdvStepsLV.ModifyCol(4, 80)
mapAdvStepsLV.ModifyCol(5, 80)
mapAdvStepsLV.ModifyCol(6, 80)
mapAdvStepsLV.ModifyCol(7, 90)
mapAdvStepsLV.OnEvent("Click", (*) => MapAdvLoadEditorFromSelection())

MapAdvGui.AddGroupBox("x20 y235 w600 h175", "Step Editor")
MapAdvGui.AddText("x40 y260", "Type:")
mapAdvTypeDdl := MapAdvGui.AddDropDownList("x90 y257 w160", ["Drag", "Zoom Out"])
mapAdvTypeDdl.Text := "Drag"
mapAdvTypeDdl.OnEvent("Change", (*) => UpdateMapAdvEditorLabels())

mapAdvXLabel := MapAdvGui.AddText("x40 y295", "X:")
mapAdvXEdit := MapAdvGui.AddEdit("x65 y292 w60", "0")
mapAdvYLabel := MapAdvGui.AddText("x140 y295", "Y:")
mapAdvYEdit := MapAdvGui.AddEdit("x165 y292 w60", "0")
mapAdvPosBtn := MapAdvGui.AddButton("x240 y291 w110", "Set Position")
mapAdvPosBtn.OnEvent("Click", StartCapture.Bind(mapAdvXEdit, mapAdvYEdit))

mapAdvEndXLabel := MapAdvGui.AddText("x40 y330", "End X:")
mapAdvEndXEdit := MapAdvGui.AddEdit("x95 y327 w60", "0")
mapAdvEndYLabel := MapAdvGui.AddText("x170 y330", "End Y:")
mapAdvEndYEdit := MapAdvGui.AddEdit("x225 y327 w60", "0")
mapAdvEndPosBtn := MapAdvGui.AddButton("x300 y326 w110", "Set Position")
mapAdvEndPosBtn.OnEvent("Click", StartCapture.Bind(mapAdvEndXEdit, mapAdvEndYEdit))
mapAdvMsLabel := MapAdvGui.AddText("x430 y330", "Drag (ms):")
mapAdvMsEdit := MapAdvGui.AddEdit("x520 y327 w60", "500")

MapAdvGui.AddButton("x40 y375 w100", "Add Step").OnEvent("Click", (*) => MapAdvAddStepClick())
MapAdvGui.AddButton("x150 y375 w130", "Update Selected").OnEvent("Click", (*) => MapAdvUpdateSelectedClick())
MapAdvGui.AddButton("x290 y375 w130", "Remove Selected").OnEvent("Click", (*) => MapAdvRemoveSelectedClick())
MapAdvGui.AddButton("x430 y375 w90", "Move Up").OnEvent("Click", (*) => MapAdvMoveUpClick())
MapAdvGui.AddButton("x530 y375 w90", "Move Down").OnEvent("Click", (*) => MapAdvMoveDownClick())

MapAdvGui.AddButton("x530 y425 w90", "Close").OnEvent("Click", (*) => CloseMapAdvGui())
MapAdvGui.OnEvent("Close", (*) => CloseMapAdvGui())

; ============================================================
; OPTION AVAILABILITY CHECK WINDOW (per-option OCR detector for "Option Select")
; ============================================================
CurrentAvailOptionIndex := 0

OptionAvailGui := Gui("+Owner" MyGui.Hwnd, "Option Availability Check")
OptionAvailGui.SetFont("s10")

optAvailLabel := OptionAvailGui.AddText("x20 y15 w490", "Editing: Option 1 availability check")

optAvailXLbl := OptionAvailGui.AddText("x20 y52", "Region1 X:")
optAvailXEdit := OptionAvailGui.AddEdit("x100 y49 w60", "0")
optAvailYLbl := OptionAvailGui.AddText("x180 y52", "Region1 Y:")
optAvailYEdit := OptionAvailGui.AddEdit("x260 y49 w60", "0")
optAvailPosBtn := OptionAvailGui.AddButton("x340 y48 w110", "Select Region")
optAvailPosBtn.OnEvent("Click", (*) => StartRegionCapture(optAvailXEdit, optAvailYEdit, optAvailEndXEdit, optAvailEndYEdit))

optAvailEndXLbl := OptionAvailGui.AddText("x20 y87", "Region2 X:")
optAvailEndXEdit := OptionAvailGui.AddEdit("x100 y84 w60", "0")
optAvailEndYLbl := OptionAvailGui.AddText("x180 y87", "Region2 Y:")
optAvailEndYEdit := OptionAvailGui.AddEdit("x260 y84 w60", "0")

optAvailTextLbl := OptionAvailGui.AddText("x20 y122", "Expected Text:")
optAvailTextEdit := OptionAvailGui.AddEdit("x120 y119 w330", "")

optAvailInvertChk := OptionAvailGui.AddCheckBox("x20 y152 w480", "Text found means UNAVAILABLE (instead of available)")
AddHelpIcon(OptionAvailGui, 505, 153, "Leave Expected Text empty to skip the detection entirely for this option - it'll be treated as available as soon as it's clicked (the old behavior). When set, after clicking the option this region is scanned and compared: normally, finding the text means the option IS available; check the box above if your game does it the other way around (e.g. the text only appears when the option is greyed out/locked).")

optAvailTestBtn := OptionAvailGui.AddButton("x20 y185 w110", "Test OCR")
optAvailTestBtn.OnEvent("Click", (*) => OptAvailTestOcrClick())
optAvailShowRegionBtn := OptionAvailGui.AddButton("x140 y185 w100", "Show Region")
optAvailShowRegionBtn.OnEvent("Click", (*) => ShowRegionPreviewFromPct(optAvailXEdit.Value, optAvailYEdit.Value, optAvailEndXEdit.Value, optAvailEndYEdit.Value))
optAvailResultText := OptionAvailGui.AddEdit("x250 y187 w260 h22 ReadOnly -WantReturn -E0x200", "OCR result will appear here.")

; Convenience for the common case where every option shows the same "no attempts left" indicator
; in the same spot regardless of which one was clicked - no need to set up the same region/text
; 3 times by hand.
optAvailApplyAllBtn := OptionAvailGui.AddButton("x20 y222 w220", "Apply to All 3 Options")
optAvailApplyAllBtn.OnEvent("Click", (*) => OptAvailApplyToAllClick())
AddHelpIcon(OptionAvailGui, 245, 224, "Copies the region/text/invert settings currently shown above to all 3 options at once - handy when every option's availability shows up the same way in the same place, so you only have to set it up once.")

OptionAvailGui.AddButton("x420 y260 w90", "Close").OnEvent("Click", (*) => CloseOptionAvailGui())
OptionAvailGui.OnEvent("Close", (*) => CloseOptionAvailGui())

; ============================================================
; ADVANCED DETECTION OUTCOMES WINDOW (per "Custom Detection" step, when "Advanced" is checked)
; ============================================================
; Edits EditingOutcomes (the currently-open Step Editor step's outcome list) - not committed to
; the step until "Add Step"/"Update Selected" is clicked in the main Step Editor, same as every
; other field there.
AdvDetGui := Gui("+Owner" EditGui.Hwnd, "Advanced Detection Outcomes")
AdvDetGui.SetFont("s10")

AdvDetGui.AddText("x20 y15 w600", "Each outcome's Name doubles as the OCR expected text matched against this step's Region1/Region2. Checked top-to-bottom - the first match wins.")

advDetLV := AdvDetGui.AddListView("x20 y50 w500 h180 Grid", ["#", "Name / Expected Text", "Screen ->"])
advDetLV.ModifyCol(1, 30)
advDetLV.ModifyCol(2, 260)
advDetLV.ModifyCol(3, 190)
advDetLV.OnEvent("Click", (*) => AdvDetLoadEditorFromSelection())

AdvDetGui.AddText("x20 y245", "Name / Expected Text:")
advDetNameEdit := AdvDetGui.AddEdit("x160 y242 w200", "")
AdvDetGui.AddText("x380 y245", "Screen ->")
advDetScreenDdl := AdvDetGui.AddDropDownList("x440 y242 w190")

AdvDetGui.AddButton("x20 y280 w100", "Add").OnEvent("Click", (*) => AdvDetAddClick())
AdvDetGui.AddButton("x130 y280 w130", "Update Selected").OnEvent("Click", (*) => AdvDetUpdateClick())
AdvDetGui.AddButton("x270 y280 w130", "Remove Selected").OnEvent("Click", (*) => AdvDetRemoveClick())
AdvDetGui.AddButton("x410 y280 w90", "Move Up").OnEvent("Click", (*) => AdvDetMoveUpClick())
AdvDetGui.AddButton("x510 y280 w90", "Move Down").OnEvent("Click", (*) => AdvDetMoveDownClick())
AddHelpIcon(AdvDetGui, 605, 17, "'Screen ->' accepts '(continue)' (fall through to the next step), '(Repeat)' (re-run this step - see the Fallback-after-N-attempts safety net above it), '(Stop Macro)', or any screen name.")

AdvDetGui.AddButton("x510 y320 w90", "Close").OnEvent("Click", (*) => CloseAdvDetGui())
AdvDetGui.OnEvent("Close", (*) => CloseAdvDetGui())

; ============================================================
; REMOTE AGENT SETUP WINDOW (pair + start/stop the companion agent, remote/agent)
; ============================================================
; Pairing is account-based: the user's remote-control account email/password (created here on the
; spot via "Register", or an existing one via "Log in") IS the pairing credential - there is no
; separate one-time code to generate on the dashboard and copy back. This window still does NOT put
; any networking or JSON parsing inside the macro itself (see the "Remote access initiative" section
; of CLAUDE.md - the macro stays network-free) - it only launches the SAME agent .exe a user would
; otherwise run by hand, exactly like EnsureOcrServer already launches the OCR helper. The agent
; writes its own plain-text result (never the password or the device token) to a temp file via
; --auth-result-file so the outcome can be shown here without capturing stdout through a shell.
;
; The password (and TOTP code, if any) are handed to the agent through a small temp file
; (--credentials-file) rather than as a command-line argument: other processes on the same machine
; can enumerate another process's command line (e.g. via WMI), which is fine for a short-lived
; pairing code but not for an account password. The agent reads and deletes that file immediately;
; this window ALSO deletes it right after the agent exits, as a defense-in-depth backstop in case the
; agent could not be launched at all.
;
; Every value that becomes part of the launched command line (agent path, server URL, email,
; credentials-file/result-file paths) MUST go through WinArgQuote - Run/RunWait invoke CreateProcess
; directly for a plain "<exe> <params>" target (no cmd.exe), so that quoting is the only thing
; standing between arbitrary user input and a second argument/flag being injected into the agent
; process.
RemoteAgentPairBusy := false
RemoteAgentGui := Gui("+Owner" MyGui.Hwnd, "Remote Agent Setup")
RemoteAgentGui.SetFont("s10")

RemoteAgentGui.AddText("x20 y15 w670", "Pairs this PC with your Anime Expedition remote-control account and starts the background agent - no command line needed. Log in with an existing account, or register a new one, right here.")

RemoteAgentGui.AddText("x20 y70", "Agent executable:")
remoteAgentPathEdit := RemoteAgentGui.AddEdit("x150 y67 w370", "")
remoteAgentBrowseBtn := RemoteAgentGui.AddButton("x525 y66 w90", "Browse...")
remoteAgentBrowseBtn.OnEvent("Click", (*) => RemoteAgentBrowseClick())
AddHelpIcon(RemoteAgentGui, 625, 68, "Path to animeexpedition-agent.exe - bundled automatically with the installed app, so this is usually already filled in. Only needs to be set once - it is remembered; Browse manually only if you moved or built your own copy (see remote/README.md).")

RemoteAgentGui.AddText("x20 y107", "Server URL:")
remoteServerUrlEdit := RemoteAgentGui.AddEdit("x150 y104 w370", "")
AddHelpIcon(RemoteAgentGui, 525, 106, "The backend base URL shown by the web dashboard, e.g. http://localhost:8787 while testing locally.")

RemoteAgentGui.AddText("x20 y144", "Account:")
remoteLoginRadio := RemoteAgentGui.AddRadio("x150 y144 w90 Checked", "Log in")
remoteRegisterRadio := RemoteAgentGui.AddRadio("x245 y144 w100", "Register")
AddHelpIcon(RemoteAgentGui, 350, 146, "Log in pairs this device to an account you already created (on this dashboard or another device). Register creates a brand new account and pairs this device to it in one step.")

RemoteAgentGui.AddText("x20 y181", "Email:")
remoteEmailEdit := RemoteAgentGui.AddEdit("x150 y178 w300", "")

RemoteAgentGui.AddText("x20 y218", "Password:")
remotePasswordEdit := RemoteAgentGui.AddEdit("x150 y215 w300 Password", "")

RemoteAgentGui.AddText("x20 y255", "2FA code:")
remoteTotpEdit := RemoteAgentGui.AddEdit("x150 y252 w100", "")
AddHelpIcon(RemoteAgentGui, 258, 254, "Only needed for Log in, and only if the account has two-factor authentication enabled. Leave blank otherwise; if one is required, this window will say so and you can fill it in and click Pair again.")

remotePairBtn := RemoteAgentGui.AddButton("x150 y292 w150", "Pair")
remotePairBtn.OnEvent("Click", (*) => RemoteAgentPairClick())

remoteAgentStatusText := RemoteAgentGui.AddText("x20 y334 w670", "Agent: not running.")

remoteAgentStartBtn := RemoteAgentGui.AddButton("x20 y359 w120", "Start Agent")
remoteAgentStartBtn.OnEvent("Click", (*) => RemoteAgentStartClick())
remoteAgentStopBtn := RemoteAgentGui.AddButton("x150 y359 w120", "Stop Agent")
remoteAgentStopBtn.OnEvent("Click", (*) => RemoteAgentStopClick())
AddHelpIcon(RemoteAgentGui, 280, 361, "The agent is a separate background process - it keeps running (and reporting status) independently of this window and of the macro's own Start/Stop, so it is NOT stopped automatically when this app closes.")

remoteAgentResultText := RemoteAgentGui.AddEdit("x20 y394 w670 h110 ReadOnly VScroll -WantReturn", "")

RemoteAgentGui.AddButton("x600 y516 w90", "Close").OnEvent("Click", (*) => CloseRemoteAgentGui())
RemoteAgentGui.OnEvent("Close", (*) => CloseRemoteAgentGui())

; Shows the window prefilled with the remembered agent path/server URL/email (or a sensible default -
; the bundled release copy, or a built dev/source checkout - see DefaultRemoteAgentPath) and a fresh
; status line. The password and
; 2FA code are never remembered, and the mode always resets to "Log in".
OpenRemoteAgentGui(*) {
    global remoteAgentPathEdit, remoteServerUrlEdit, remoteLoginRadio, remoteRegisterRadio
    global remoteEmailEdit, remotePasswordEdit, remoteTotpEdit, remoteAgentResultText
    global RemoteAgentPairBusy

    path := Cfg("General", "RemoteAgentPath", "")
    if (path = "" || !FileExist(path))
        path := DefaultRemoteAgentPath()
    remoteAgentPathEdit.Value := path

    serverUrl := Cfg("General", "RemoteServerUrl", "")
    remoteServerUrlEdit.Value := (serverUrl != "" ? serverUrl : "http://localhost:8787")

    remoteEmailEdit.Value := Cfg("General", "RemoteAccountEmail", "")
    if !RemoteAgentPairBusy {
        remoteLoginRadio.Value := 1
        remoteRegisterRadio.Value := 0
        remotePasswordEdit.Value := ""
        remoteTotpEdit.Value := ""
        remoteAgentResultText.Text := ""
    }
    RefreshRemoteAgentStatus()
    RemoteAgentGui.Show("w710 h560")
}

CloseRemoteAgentGui(*) {
    global remoteAgentPathEdit, remoteServerUrlEdit, remoteEmailEdit, remotePasswordEdit, remoteTotpEdit, ConfigFile
    path := Trim(remoteAgentPathEdit.Value)
    if (path != "")
        IniWrite path, ConfigFile, "General", "RemoteAgentPath"
    serverUrl := Trim(remoteServerUrlEdit.Value)
    if (serverUrl != "")
        IniWrite serverUrl, ConfigFile, "General", "RemoteServerUrl"
    email := Trim(remoteEmailEdit.Value)
    if (email != "")
        IniWrite email, ConfigFile, "General", "RemoteAccountEmail"
    ; Hiding does not destroy the controls, so a password left in the field (e.g. the "enter your
    ; 2FA code and retry" case preserves it - see RemoteAgentPairClick) would otherwise sit in memory
    ; for as long as the app keeps running, not just until the next OpenRemoteAgentGui reset.
    remotePasswordEdit.Value := ""
    remoteTotpEdit.Value := ""
    RemoteAgentGui.Hide()
}

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

RemoteAgentBrowseClick(*) {
    global remoteAgentPathEdit, ConfigFile
    file := FileSelect(3, remoteAgentPathEdit.Value, "Locate animeexpedition-agent.exe", "Agent executable (*.exe)")
    if (file = "")
        return
    remoteAgentPathEdit.Value := file
    IniWrite file, ConfigFile, "General", "RemoteAgentPath"
}

; The base filename of whatever path is currently set (e.g. "animeexpedition-agent.exe", or
; whatever the user actually renamed/selected) - falls back to the documented default name only
; while the field is still empty, so detection/start/stop always target the SAME exe the user
; configured instead of a hardcoded name that could silently stop matching a renamed binary.
RemoteAgentExeName(agentPath := unset) {
    if !IsSet(agentPath) {
        global remoteAgentPathEdit
        agentPath := remoteAgentPathEdit.Value
    }
    path := Trim(agentPath)
    if (path = "")
        return "animeexpedition-agent.exe"
    SplitPath path, &name
    return (name != "") ? name : "animeexpedition-agent.exe"
}

; Detects the agent by executable name rather than a remembered PID, so status is correct even
; right after this app restarts - the agent is meant to keep running independently (see the Start/
; Stop help icon above), so nothing here tracks "the PID we personally launched".
RemoteAgentRunningPid(agentPath := unset) {
    return IsSet(agentPath) ? ProcessExist(RemoteAgentExeName(agentPath)) : ProcessExist(RemoteAgentExeName())
}

RefreshRemoteAgentStatus() {
    global remoteAgentStatusText
    pid := RemoteAgentRunningPid()
    remoteAgentStatusText.Text := pid ? "Agent: running (PID " pid ")." : "Agent: not running."
}

; Signs in to (or registers) the account and pairs this device by launching the SAME agent .exe a
; user would otherwise run by hand (`--login|--register --email <email> --credentials-file <file>
; --server <url>`), plus --auth-result-file so the agent's own success/error text can be read back
; without capturing stdout through a shell. The process runs in the background and is polled with a
; timer so a slow server cannot freeze this window or the macro's main GUI.
RemoteAgentSetPairingControlsEnabled(enabled) {
    global remoteAgentPathEdit, remoteServerUrlEdit, remoteLoginRadio, remoteRegisterRadio
    global remoteEmailEdit, remotePasswordEdit, remoteTotpEdit, remotePairBtn
    global remoteAgentBrowseBtn, remoteAgentStartBtn, remoteAgentStopBtn
    for ctrl in [remoteAgentPathEdit, remoteServerUrlEdit, remoteLoginRadio, remoteRegisterRadio,
                 remoteEmailEdit, remotePasswordEdit, remoteTotpEdit, remotePairBtn,
                 remoteAgentBrowseBtn, remoteAgentStartBtn, remoteAgentStopBtn]
        ctrl.Enabled := enabled
}

RemoteAgentPairClick(*) {
    global remoteAgentPathEdit, remoteServerUrlEdit, remoteLoginRadio, remoteRegisterRadio
    global remoteEmailEdit, remotePasswordEdit, remoteTotpEdit, remoteAgentResultText, ConfigFile
    global RemoteAgentPairBusy, RemoteAgentPairPid, RemoteAgentPairResultFile
    global RemoteAgentPairCredentialsFile, RemoteAgentPairAgentPath, RemoteAgentPairDeadline

    if RemoteAgentPairBusy
        return

    agentPath := Trim(remoteAgentPathEdit.Value)
    serverUrl := Trim(remoteServerUrlEdit.Value)
    email := Trim(remoteEmailEdit.Value)
    password := remotePasswordEdit.Value   ; not trimmed - a password may legitimately have edge whitespace
    totp := Trim(remoteTotpEdit.Value)
    modeFlag := remoteRegisterRadio.Value ? "--register" : "--login"

    if (agentPath = "" || !FileExist(agentPath)) {
        remoteAgentResultText.Text := "Set a valid path to animeexpedition-agent.exe first (Browse...)."
        return
    }
    if (serverUrl = "") {
        remoteAgentResultText.Text := "Enter the server URL first."
        return
    }
    if (email = "") {
        remoteAgentResultText.Text := "Enter the account email first."
        return
    }
    if (password = "") {
        remoteAgentResultText.Text := "Enter the account password first."
        return
    }

    uniqueSuffix := DllCall("GetCurrentProcessId") "-" A_TickCount
    resultFile := A_Temp "\anime-expedition-auth-result-" uniqueSuffix ".txt"
    credentialsFile := A_Temp "\anime-expedition-credentials-" uniqueSuffix ".txt"
    try FileDelete resultFile
    try FileDelete credentialsFile

    ; The password (and TOTP) never touch the command line - see the block comment above this
    ; window's construction. Written with restrictive default ACLs implied by living under this
    ; user's own %TEMP%, same as the existing result-file scratch files in this GUI. UTF-8-RAW (not
    ; plain UTF-8) is required here: plain "UTF-8" makes FileAppend prepend a byte-order mark to a
    ; brand-new file, and the Go agent's os.ReadFile does NOT strip it - that BOM would silently
    ; become part of the "password" line the agent reads, breaking login for any pre-existing
    ; account (an already-registered password never contains it) while masking itself on --register
    ; (a fresh account simply adopts the BOM-prefixed string as its real password).
    try {
        IniWrite agentPath, ConfigFile, "General", "RemoteAgentPath"
        IniWrite serverUrl, ConfigFile, "General", "RemoteServerUrl"
        IniWrite email, ConfigFile, "General", "RemoteAccountEmail"
        FileAppend(password "`n" totp, credentialsFile, "UTF-8-RAW")
    } catch as err {
        try FileDelete credentialsFile
        remoteAgentResultText.Text := "Could not prepare account pairing: " err.Message
        return
    }

    cmd := WinArgQuote(agentPath)
        . " --server " WinArgQuote(serverUrl)
        . " " modeFlag
        . " --email " WinArgQuote(email)
        . " --credentials-file " WinArgQuote(credentialsFile)
        . " --auth-result-file " WinArgQuote(resultFile)

    RemoteAgentPairBusy := true
    RemoteAgentSetPairingControlsEnabled(false)
    remoteAgentResultText.Text := "Pairing..."
    pid := 0
    try {
        Run(cmd, , "Hide", &pid)
    } catch as err {
        try FileDelete credentialsFile
        RemoteAgentPairBusy := false
        RemoteAgentSetPairingControlsEnabled(true)
        remoteAgentResultText.Text := "Could not launch the agent: " err.Message
        return
    }

    RemoteAgentPairPid := pid
    RemoteAgentPairResultFile := resultFile
    RemoteAgentPairCredentialsFile := credentialsFile
    RemoteAgentPairAgentPath := agentPath
    ; A little above the agent's own HTTP timeout: requests remain responsive without cancelling a
    ; legitimately slow sign-in or registration.
    RemoteAgentPairDeadline := A_TickCount + 40000
    SetTimer RemoteAgentPairPoll, 200
}

RemoteAgentPairPoll() {
    global RemoteAgentPairBusy, RemoteAgentPairPid, RemoteAgentPairResultFile
    global RemoteAgentPairCredentialsFile, RemoteAgentPairDeadline, remoteAgentResultText

    if !ProcessExist(RemoteAgentPairPid) {
        SetTimer RemoteAgentPairPoll, 0
        RemoteAgentPairFinish()
        return
    }
    if (A_TickCount < RemoteAgentPairDeadline)
        return

    try ProcessClose(RemoteAgentPairPid)
    if (A_TickCount > RemoteAgentPairDeadline + 5000) {
        SetTimer RemoteAgentPairPoll, 0
        try FileDelete RemoteAgentPairResultFile
        try FileDelete RemoteAgentPairCredentialsFile
        RemoteAgentPairBusy := false
        RemoteAgentSetPairingControlsEnabled(true)
        remoteAgentResultText.Text := "Pairing timed out and the unresponsive agent could not be stopped - check Task Manager for a stuck animeexpedition-agent.exe."
    }
}

RemoteAgentPairFinish() {
    global remoteAgentResultText, remotePasswordEdit, remoteTotpEdit
    global RemoteAgentPairBusy, RemoteAgentPairResultFile, RemoteAgentPairCredentialsFile, RemoteAgentPairAgentPath

    message := ""
    try message := Trim(FileRead(RemoteAgentPairResultFile, "UTF-8"))
    try FileDelete RemoteAgentPairResultFile
    try FileDelete RemoteAgentPairCredentialsFile
    if (message = "")
        message := "Pairing failed (the agent exited unexpectedly)."

    ; Never leave the password sitting in the field after an attempt - EXCEPT when the account just
    ; asked for a 2FA code: that message is specifically inviting the user to add the code and click
    ; Pair again with the SAME password, so wiping it here would silently break that promise (see
    ; the friendly "totp_required" text in remote/agent/main.go's friendlyAuthError).
    if !InStr(message, "two-factor authentication enabled")
        remotePasswordEdit.Value := ""
    remoteTotpEdit.Value := ""
    LogMsg("Remote agent: " message)

    if (SubStr(message, 1, StrLen("Pairing successful")) = "Pairing successful")
        message := message "`r`n" RemoteAgentAutoStart(RemoteAgentPairAgentPath)
    RemoteAgentPairBusy := false
    RemoteAgentSetPairingControlsEnabled(true)
    remoteAgentResultText.Text := message
    RefreshRemoteAgentStatus()
}

; Launches the agent hidden in the background (long-poll mode - no --login/--register, so it uses
; the device token just saved by pairing) and does a brief liveness check, since a not-yet-paired or
; misconfigured agent exits almost immediately. Shared by the manual "Start Agent" button and by
; RemoteAgentPairClick right after a successful pairing.
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

RemoteAgentStartClick(*) {
    global remoteAgentResultText, remoteAgentPathEdit
    remoteAgentResultText.Text := RemoteAgentAutoStart(Trim(remoteAgentPathEdit.Value))
    RefreshRemoteAgentStatus()
}

RemoteAgentStopClick(*) {
    global remoteAgentResultText
    pid := RemoteAgentRunningPid()
    if !pid {
        remoteAgentResultText.Text := "Agent is not running."
        RefreshRemoteAgentStatus()
        return
    }
    try ProcessClose(pid)
    Sleep 200   ; brief grace period before checking whether it actually terminated
    if RemoteAgentRunningPid() {
        remoteAgentResultText.Text := "Could not stop the agent (PID " pid ")."
    } else {
        LogMsg("Remote agent: stopped.")
        remoteAgentResultText.Text := "Agent stopped."
    }
    RefreshRemoteAgentStatus()
}

; ---------------- MAP PROFILE BOOTSTRAP ----------------
; (must run before preset bootstrap - LoadPreset() needs defaultMapDdl already populated)
InitMapProfiles()
mapProfileDdl.OnEvent("Change", (*) => MapProfileChanged())

; ---------------- PRESET BOOTSTRAP ----------------
InitPresets()
UpdateStepEditorLabels()

if !IsHeadlessEngine
    MyGui.Show("w820 h850")
CreateMarker()

OpenEditGui(*) {
    global CurrentPresetName, EditGui, editingLabel, EditGuiVisible, EditGuiScrollY
    LoadPreset(CurrentPresetName)
    editingLabel.Text := "Editing: " CurrentPresetName
    RefreshImportPresetDdl()
    ; This window's full content is 1070px tall, which doesn't fit on plenty of screens - cap the
    ; shown height to the work area (leaving a small margin for the taskbar/title bar) instead of
    ; letting the window run off-screen. The WS_VSCROLL style set on EditGui above then shows a
    ; scrollbar so anything that doesn't fit is still reachable by scrolling.
    ; EditGui is only Show()/Hide()'d (never recreated), so if it was left scrolled down from a
    ; previous visit, its controls are still physically shifted from last time - restore them to
    ; their authored position before recomputing the range for this visit's (possibly different)
    ; screen/window size.
    if (EditGuiScrollY != 0)
        ScrollEditGuiTo(0)
    MonitorGetWorkArea(, &waLeft, &waTop, &waRight, &waBottom)
    maxHeight := (waBottom - waTop) - 40
    EditGui.Show("w860 h" Min(1070, maxHeight))
    UpdateEditGuiScrollRange()
    EditGuiVisible := true
}

CloseEditGui(*) {
    global CurrentPresetName, EditGui, EditGuiVisible
    SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
    ; Adding/removing an Option Select step here can change whether the challenge-usage box applies.
    UpdateUsageBoxVisibility(CurrentPresetName)
    EditGui.Hide()
    EditGuiVisible := false
}

; Fires whenever the Edit Preset window is resized or maximized/restored. Widens the step list
; (stepsLV) to fill the extra width instead of leaving it blank - that ListView packs 12 columns
; into a fixed width by default, which is the main thing that gets unreadably cramped. Also
; recomputes the vertical scroll range, since resizing taller/shorter changes the viewport height
; (and therefore how much of the content is already visible without scrolling).
EditGuiSizeHandler(guiObj, minMax, width, height) {
    global stepsLV
    if (minMax = -1)  ; minimized - nothing to reflow
        return
    try stepsLV.Move(, , Max(750, width - 90), )
    try UpdateEditGuiScrollRange()
}

OpenMapAdvancedGui(*) {
    global CurrentMapProfileName, MapAdvGui, mapAdvLabel, mapCustomCameraChk
    LoadMapProfile(CurrentMapProfileName)
    mapAdvLabel.Text := mapCustomCameraChk.Value
        ? "Editing: custom settings for '" CurrentMapProfileName "'"
        : "Editing: shared default (all maps without 'custom' checked)"
    MapAdvGui.Show("w650 h500")
}

CloseMapAdvGui(*) {
    global CurrentMapProfileName, MapAdvGui
    profile := BuildMapProfileSaveData()
    SaveMapProfileToIni(CurrentMapProfileName, profile.ExpectedText, profile.CustomTowers, profile.CustomNumPlacements, profile.Placements, profile.CustomCamera)
    SaveMapAdvStepsFromLV(profile.CustomCamera ? ("MapProfile_" CurrentMapProfileName) : "General")
    MapAdvGui.Hide()
}

; Opens the shared Option Availability Check popup pre-loaded with option `idx`'s (1-3) currently
; held detector settings. Bound per-option via .Bind(i) on each "Availability Check..." button.
OpenOptionAvailGui(idx, *) {
    global CurrentAvailOptionIndex, OptData, optAvailLabel, optAvailXEdit, optAvailYEdit
    global optAvailEndXEdit, optAvailEndYEdit, optAvailTextEdit, optAvailInvertChk, optAvailResultText, OptionAvailGui
    CurrentAvailOptionIndex := idx
    opt := OptData[idx]
    optAvailLabel.Text := "Editing: Option " idx " (" opt.NameEdit.Value ") availability check"
    optAvailXEdit.Value := opt.DetX
    optAvailYEdit.Value := opt.DetY
    optAvailEndXEdit.Value := opt.DetEndX
    optAvailEndYEdit.Value := opt.DetEndY
    optAvailTextEdit.Value := opt.DetText
    optAvailInvertChk.Value := opt.DetInvert
    optAvailResultText.Text := "OCR result will appear here."
    OptionAvailGui.Show("w530 h295")
}

; Flushes the popup's fields back onto the OptData entry it was opened for, then hides it. Actual
; ini persistence happens later via SavePresetToIni, same as every other option field.
CloseOptionAvailGui(*) {
    global CurrentAvailOptionIndex, OptData, optAvailXEdit, optAvailYEdit
    global optAvailEndXEdit, optAvailEndYEdit, optAvailTextEdit, optAvailInvertChk, OptionAvailGui
    if CurrentAvailOptionIndex {
        opt := OptData[CurrentAvailOptionIndex]
        opt.DetX := optAvailXEdit.Value
        opt.DetY := optAvailYEdit.Value
        opt.DetEndX := optAvailEndXEdit.Value
        opt.DetEndY := optAvailEndYEdit.Value
        opt.DetText := optAvailTextEdit.Value
        opt.DetInvert := optAvailInvertChk.Value
    }
    OptionAvailGui.Hide()
}

; ============================================================
; ADVANCED DETECTION OUTCOMES (popup for "Custom Detection" + "Advanced Detection")
; ============================================================
; Repopulates the popup's "Screen ->" dropdown from the current preset's screen list, same pseudo-
; targets as the per-step Logic Fallback dropdown (minus "(none)", since every outcome should
; always resolve to something - "(continue)" is the neutral default).
RefreshAdvDetScreenDdl() {
    global advDetScreenDdl, CurrentPresetName
    cur := advDetScreenDdl.Text
    items := ["(continue)", "(Repeat)", "(Stop Macro)"]
    for n in GetPresetScreenNames(CurrentPresetName)
        items.Push(n)
    advDetScreenDdl.Delete()
    advDetScreenDdl.Add(items)
    SelectDdlText(advDetScreenDdl, items, cur, "(continue)")
}

LoadAdvDetLV() {
    global advDetLV, EditingOutcomes
    advDetLV.Delete()
    for i, o in EditingOutcomes
        advDetLV.Add("", i, o.Name, o.Screen)
}

OpenAdvDetGui(*) {
    global EditingOutcomes, AdvDetGui
    if (EditingOutcomes.Length = 0) {
        EditingOutcomes.Push({Name: "True", Screen: "(continue)"})
        EditingOutcomes.Push({Name: "False", Screen: "(continue)"})
    }
    RefreshAdvDetScreenDdl()
    LoadAdvDetLV()
    AdvDetGui.Show("w630 h360")
}

; Flushes the ListView back into EditingOutcomes, then hides the popup - actual commit onto the
; step itself still happens later via "Add Step"/"Update Selected", same as every other field.
CloseAdvDetGui(*) {
    global advDetLV, EditingOutcomes, AdvDetGui
    arr := []
    Loop advDetLV.GetCount() {
        i := A_Index
        arr.Push({Name: advDetLV.GetText(i, 2), Screen: advDetLV.GetText(i, 3)})
    }
    EditingOutcomes := arr
    AdvDetGui.Hide()
}

AdvDetLoadEditorFromSelection(*) {
    global advDetLV, advDetNameEdit, advDetScreenDdl
    row := advDetLV.GetNext(0, "Focused")
    if !row
        return
    advDetNameEdit.Value := advDetLV.GetText(row, 2)
    SetDdlTextSafe(advDetScreenDdl, advDetLV.GetText(row, 3), "(continue)")
}

AdvDetAddClick(*) {
    global advDetLV, advDetNameEdit, advDetScreenDdl
    if (Trim(advDetNameEdit.Value) = "") {
        MsgBox "Enter a name/expected text first."
        return
    }
    advDetLV.Add("", advDetLV.GetCount() + 1, advDetNameEdit.Value, advDetScreenDdl.Text)
}

AdvDetUpdateClick(*) {
    global advDetLV, advDetNameEdit, advDetScreenDdl
    row := advDetLV.GetNext(0, "Focused")
    if !row {
        MsgBox "No outcome selected."
        return
    }
    advDetLV.Modify(row, "", row, advDetNameEdit.Value, advDetScreenDdl.Text)
}

AdvDetRemoveClick(*) {
    global advDetLV
    row := advDetLV.GetNext(0, "Focused")
    if !row
        return
    advDetLV.Delete(row)
    Loop advDetLV.GetCount()
        advDetLV.Modify(A_Index, "", A_Index)
}

AdvDetSwapRows(r1, r2) {
    global advDetLV
    n1 := advDetLV.GetText(r1, 2), s1 := advDetLV.GetText(r1, 3)
    n2 := advDetLV.GetText(r2, 2), s2 := advDetLV.GetText(r2, 3)
    advDetLV.Modify(r1, "", r1, n2, s2)
    advDetLV.Modify(r2, "", r2, n1, s1)
}

AdvDetMoveUpClick(*) {
    global advDetLV
    row := advDetLV.GetNext(0, "Focused")
    if (!row || row = 1)
        return
    AdvDetSwapRows(row, row - 1)
    advDetLV.Modify(row - 1, "Focus Select")
}

AdvDetMoveDownClick(*) {
    global advDetLV
    row := advDetLV.GetNext(0, "Focused")
    n := advDetLV.GetCount()
    if (!row || row = n)
        return
    AdvDetSwapRows(row, row + 1)
    advDetLV.Modify(row + 1, "Focus Select")
}

; Tests whatever's currently entered in the popup (not necessarily saved to OptData yet).
OptAvailTestOcrClick(*) {
    global optAvailXEdit, optAvailYEdit, optAvailEndXEdit, optAvailEndYEdit, optAvailTextEdit, optAvailResultText
    a := AbsXY(optAvailXEdit.Value, optAvailYEdit.Value)
    b := AbsXY(optAvailEndXEdit.Value, optAvailEndYEdit.Value)
    rect := {x: Min(a.x, b.x), y: Min(a.y, b.y), w: Abs(b.x - a.x), h: Abs(b.y - a.y)}
    if (rect.w <= 0 || rect.h <= 0) {
        MsgBox "Set both Region1 and Region2 positions first."
        return
    }
    optAvailResultText.Text := "Reading..."
    text := RunOcrOnRegion(rect.x, rect.y, rect.w, rect.h)
    if (text = "") {
        optAvailResultText.Text := "(no text recognized)"
        LogMsg("Option availability OCR test: (no text recognized)")
        return
    }
    expected := optAvailTextEdit.Value
    isMatch := (expected != "") && (InStr(text, expected) || TextContainsPartialMatch(text, expected, 6))
    optAvailResultText.Text := "Recognized: '" text "' -> " (isMatch ? "MATCH" : "no match")
    LogMsg("Option availability OCR test result: '" text "'")
}

; Copies the popup's currently-entered detector settings (region + expected text + invert) to ALL
; 3 options at once - the common case is every option showing the same "no attempts left"
; indicator in the same spot regardless of which one was clicked, so there's no need to set up
; the same region/text 3 separate times.
OptAvailApplyToAllClick(*) {
    global OptData, optAvailXEdit, optAvailYEdit, optAvailEndXEdit, optAvailEndYEdit, optAvailTextEdit, optAvailInvertChk
    for opt in OptData {
        opt.DetX := optAvailXEdit.Value
        opt.DetY := optAvailYEdit.Value
        opt.DetEndX := optAvailEndXEdit.Value
        opt.DetEndY := optAvailEndYEdit.Value
        opt.DetText := optAvailTextEdit.Value
        opt.DetInvert := optAvailInvertChk.Value
    }
    LogMsg("Availability Check settings applied to all 3 options.")
    MsgBox "Applied to all 3 options."
}

; ============================================================
; PLACEMENT ROW VISIBILITY
; ============================================================
UpdatePlacementVisibility(*) {
    global numPlaceDdl, PlaceData, mapCustomTowersChk, mapNumPlaceLbl, mapNumPlaceDdl
    customOn := mapCustomTowersChk.Value
    n := customOn ? Integer(mapNumPlaceDdl.Text) : Integer(numPlaceDdl.Text)
    mapNumPlaceLbl.Visible := customOn
    mapNumPlaceDdl.Visible := customOn
    for i, row in PlaceData {
        vis := (i <= n)
        row.Label.Visible := vis
        row.XLbl.Visible := vis
        row.XEdit.Visible := vis
        row.YLbl.Visible := vis
        row.YEdit.Visible := vis
        row.PosBtn.Visible := vis
        row.CustomSlotDdl.Visible := vis && customOn
        row.CustomSlotLabel.Visible := vis && customOn
    }
}

UpdateGeneralSlotVisibility(*) {
    global numPlaceDdl, GeneralSlotDdls
    n := Integer(numPlaceDdl.Text)
    for i, ddl in GeneralSlotDdls
        ddl.Visible := (i <= n)
}

; ============================================================
; MAP PROFILE MANAGEMENT (placement coordinates, auto-detected per map)
; ============================================================
InitMapProfiles() {
    global ConfigFile, MapProfileNames, CurrentMapProfileName, mapProfileDdl, defaultMapDdl

    listStr := Cfg("MapProfiles", "List", "")

    ; One-time migration: earlier versions stored NumPlacements/slots per map profile.
    ; If General doesn't have them yet, lift them from whichever profile has them.
    if (Cfg("General", "NumPlacements", "") = "") {
        legacySource := ""
        if (listStr != "") {
            candidates := StrSplit(listStr, ",")
            for n in candidates {
                if (Cfg("MapProfile_" n, "NumPlacements", "") != "") {
                    legacySource := n
                    break
                }
            }
        }
        if (legacySource != "") {
            IniWrite Cfg("MapProfile_" legacySource, "NumPlacements", "4"), ConfigFile, "General", "NumPlacements"
            Loop 10 {
                i := A_Index
                IniWrite Cfg("MapProfile_" legacySource, "Placement" i "Slot", "1"), ConfigFile, "General", "Slot" i
            }
        } else {
            IniWrite "4", ConfigFile, "General", "NumPlacements"
            Loop 10 {
                i := A_Index
                IniWrite Cfg("Placement" i, "Slot", "1"), ConfigFile, "General", "Slot" i
            }
        }
    }

    if (listStr = "") {
        ; First run: migrate the old single placement config (if any) into a "Default" profile
        IniWrite "", ConfigFile, "MapProfile_Default", "ExpectedText"
        IniWrite 0, ConfigFile, "MapProfile_Default", "CustomTowers"
        Loop 10 {
            i := A_Index
            IniWrite Cfg("Placement" i, "X", "0"), ConfigFile, "MapProfile_Default", "Placement" i "X"
            IniWrite Cfg("Placement" i, "Y", "0"), ConfigFile, "MapProfile_Default", "Placement" i "Y"
        }
        IniWrite "Default", ConfigFile, "MapProfiles", "List"
        IniWrite "Default", ConfigFile, "MapProfiles", "Active"
        listStr := "Default"
    }

    MapProfileNames := StrSplit(listStr, ",")
    mapProfileDdl.Delete()
    mapProfileDdl.Add(MapProfileNames)

    active := Cfg("MapProfiles", "Active", MapProfileNames[1])
    found := false
    for n in MapProfileNames {
        if (n = active)
            found := true
    }
    if !found
        active := MapProfileNames[1]

    mapProfileDdl.Text := active
    CurrentMapProfileName := active
    LoadGeneralSlots()
    LoadMapProfile(CurrentMapProfileName)

    ; Populates defaultMapDdl's item list (its selected value is set per-preset by LoadPreset(),
    ; called later during preset bootstrap - which must run after this).
    RebuildDefaultMapDdl()
}

; Keeps the "Default Map" dropdown (Preset Settings tab) in sync with the current list of
; map profiles. Always offers "(none)" so detection can be required with no fallback.
RebuildDefaultMapDdl() {
    global defaultMapDdl, MapProfileNames
    current := defaultMapDdl.Text
    defaultMapDdl.Delete()
    defaultMapDdl.Add(["(none)"])
    defaultMapDdl.Add(MapProfileNames)
    found := false
    for n in MapProfileNames {
        if (n = current)
            found := true
    }
    defaultMapDdl.Text := found ? current : "(none)"
}

LoadGeneralSlots() {
    global numPlaceDdl, GeneralSlotDdls
    numPlaceDdl.Text := Cfg("General", "NumPlacements", "4")
    Loop 10 {
        i := A_Index
        GeneralSlotDdls[i].Text := Cfg("General", "Slot" i, "1")
    }
    UpdateGeneralSlotVisibility()
}

LoadMapProfile(name) {
    global PlaceData, mapExpectedTextEdit, mapCustomTowersChk, mapCustomCameraChk, mapNumPlaceDdl
    section := "MapProfile_" name
    mapExpectedTextEdit.Value := Cfg(section, "ExpectedText", "")
    mapCustomTowersChk.Value := Integer(Cfg(section, "CustomTowers", "0"))
    mapNumPlaceDdl.Text := Cfg(section, "CustomNumPlacements", "4")
    Loop 10 {
        i := A_Index
        row := PlaceData[i]
        row.XEdit.Value := Cfg(section, "Placement" i "X", "0")
        row.YEdit.Value := Cfg(section, "Placement" i "Y", "0")
        row.CustomSlotDdl.Text := Cfg(section, "CustomSlot" i, "1")
    }
    ; Map actions (Drag/Zoom Out) are shared ([General]) unless this map opts into its own copy.
    mapCustomCameraChk.Value := Integer(Cfg(section, "CustomCamera", "0"))
    LoadMapAdvStepsForProfile(name)
    UpdatePlacementVisibility()
}

; Loads the map-actions ListView (Advanced Settings) from whichever section is currently in
; effect for `name` - its own section if "custom" is checked, otherwise [General]. Does NOT touch
; mapCustomCameraChk itself, so it's safe to call right after the user toggles it.
LoadMapAdvStepsForProfile(name) {
    global mapCustomCameraChk
    section := "MapProfile_" name
    camSection := mapCustomCameraChk.Value ? section : "General"
    LoadMapAdvStepsLV(camSection)
}

OnMapCustomCameraToggled(*) {
    global CurrentMapProfileName
    LoadMapAdvStepsForProfile(CurrentMapProfileName)
}

; Snapshots the Map Profile editor's control values as plain data for SaveMapProfileToIni().
BuildMapProfileSaveData() {
    global PlaceData, mapExpectedTextEdit, mapCustomTowersChk, mapCustomCameraChk, mapNumPlaceDdl
    placements := []
    for row in PlaceData
        placements.Push({CustomSlot: row.CustomSlotDdl.Text, X: row.XEdit.Value, Y: row.YEdit.Value})
    return {ExpectedText: mapExpectedTextEdit.Value, CustomTowers: mapCustomTowersChk.Value,
        CustomNumPlacements: mapNumPlaceDdl.Text, Placements: placements, CustomCamera: mapCustomCameraChk.Value}
}

; Writes one map profile's own fields from explicit plain data. Camera/zoom steps are deliberately
; saved separately by GUI callers through SaveMapAdvStepsFromLV(), so IPC callers need not touch a ListView.
SaveMapProfileToIni(name, expectedText, customTowers, customNumPlacements, placements, customCamera) {
    global ConfigFile
    section := "MapProfile_" name
    IniWrite expectedText, ConfigFile, section, "ExpectedText"
    IniWrite customTowers, ConfigFile, section, "CustomTowers"
    IniWrite customNumPlacements, ConfigFile, section, "CustomNumPlacements"
    for i, row in placements {
        IniWrite row.CustomSlot, ConfigFile, section, "CustomSlot" i
        IniWrite row.X, ConfigFile, section, "Placement" i "X"
        IniWrite row.Y, ConfigFile, section, "Placement" i "Y"
    }
    IniWrite customCamera, ConfigFile, section, "CustomCamera"
}

RebuildMapProfileDdl() {
    global mapProfileDdl, MapProfileNames
    mapProfileDdl.Delete()
    mapProfileDdl.Add(MapProfileNames)
}

MapProfileChanged(*) {
    global CurrentMapProfileName, mapProfileDdl, ConfigFile
    if (CurrentMapProfileName != "") {
        profile := BuildMapProfileSaveData()
        SaveMapProfileToIni(CurrentMapProfileName, profile.ExpectedText, profile.CustomTowers, profile.CustomNumPlacements, profile.Placements, profile.CustomCamera)
        SaveMapAdvStepsFromLV(profile.CustomCamera ? ("MapProfile_" CurrentMapProfileName) : "General")
    }
    CurrentMapProfileName := mapProfileDdl.Text
    LoadMapProfile(CurrentMapProfileName)
    IniWrite CurrentMapProfileName, ConfigFile, "MapProfiles", "Active"
}

; Creates a map profile from an explicit name and returns a bridge-friendly result. The default
; profile data is constructed directly (not read back from the map-profile controls); those
; controls are still written afterward so the legacy GUI stays synchronized for display. Only
; prompting and destructive confirmation stay in the Click wrappers.
CreateMapProfile(name) {
    global CurrentMapProfileName, mapProfileDdl, MapProfileNames, ConfigFile, PlaceData, mapExpectedTextEdit, mapCustomTowersChk, mapCustomCameraChk, mapNumPlaceDdl
    name := Trim(name)
    if (name = "")
        return {ok: false, msg: ""}
    for n in MapProfileNames {
        if (n = name)
            return {ok: false, msg: "A map profile with this name already exists."}
    }
    if (CurrentMapProfileName != "") {
        profile := BuildMapProfileSaveData()
        SaveMapProfileToIni(CurrentMapProfileName, profile.ExpectedText, profile.CustomTowers, profile.CustomNumPlacements, profile.Placements, profile.CustomCamera)
        SaveMapAdvStepsFromLV(profile.CustomCamera ? ("MapProfile_" CurrentMapProfileName) : "General")
    }
    MapProfileNames.Push(name)
    mapProfileDdl.Add([name])
    mapProfileDdl.Text := name
    CurrentMapProfileName := name
    mapExpectedTextEdit.Value := name
    mapCustomTowersChk.Value := 0
    mapNumPlaceDdl.Text := "4"
    for row in PlaceData {
        row.CustomSlotDdl.Text := "1"
        row.XEdit.Value := "0"
        row.YEdit.Value := "0"
    }
    ; New maps start on the shared camera/zoom default (not their own custom copy).
    mapCustomCameraChk.Value := 0
    LoadMapAdvStepsForProfile(name)
    UpdatePlacementVisibility()
    ; Build the new profile's default data directly, rather than reading it back out of the native
    ; GUI controls just written above - same reasoning as CreatePreset(). A brand-new profile has no
    ; custom camera/zoom steps of its own yet (CustomCamera defaults to 0, i.e. it uses [General]'s
    ; SHARED steps as-is) so, unlike the pre-existing code, this does NOT also call
    ; SaveMapAdvStepsFromLV("General") - that used to round-trip whatever the shared mapAdvStepsLV
    ; control currently held back onto [General], a harmless no-op only because nothing had touched
    ; the control in between, not something this function should depend on at all.
    defaultPlacements := []
    Loop 10
        defaultPlacements.Push({CustomSlot: "1", X: 0, Y: 0})
    SaveMapProfileToIni(name, name, false, 4, defaultPlacements, false)
    IniWrite JoinList(MapProfileNames), ConfigFile, "MapProfiles", "List"
    IniWrite CurrentMapProfileName, ConfigFile, "MapProfiles", "Active"
    RebuildDefaultMapDdl()
    LogMsg("Map profile '" name "' created.")
    return {ok: true, msg: "Map profile '" name "' created."}
}

NewMapProfileClick(*) {
    ib := InputBox("Enter a name for the new map profile (e.g. the map name):", "New Map Profile")
    if (ib.Result != "OK" || Trim(ib.Value) = "")
        return
    result := CreateMapProfile(Trim(ib.Value))
    if !result.ok
        MsgBox result.msg
}

; Renames a map profile using explicit old/new names. It intentionally retains the legacy GUI
; snapshot and control refreshes; callers that need a prompt or dialog use RenameMapProfileClick().
RenameMapProfile(oldName, newName) {
    global CurrentMapProfileName, mapProfileDdl, MapProfileNames, ConfigFile, Running
    newName := Trim(newName)
    if (newName = "" || newName = oldName)
        return {ok: false, msg: ""}
    ; Unlike a preset, there is no "RunningMapProfileName" pinned for the whole run - the active map
    ; is detected fresh, mid-run, against a snapshot of every profile name taken just before the
    ; detection loop starts. A narrower "not THIS specific name" guard would still leave that
    ; detection race, so reject any map profile rename while a run is in progress at all.
    if Running
        return {ok: false, msg: "Cannot rename a map profile while the macro is running - stop it first."}
    for n in MapProfileNames {
        if (n = newName)
            return {ok: false, msg: "A map profile with this name already exists."}
    }
    ; Only the currently-viewed profile can have unsaved in-editor edits (BuildMapProfileSaveData()
    ; snapshots whatever's live in the GUI, regardless of which name it's told to save under) -
    ; renaming a different, not-currently-viewed profile instead copies its already-persisted
    ; section as-is (CopyIniSection copies the whole section, so custom camera/zoom steps that
    ; live in that same section come along automatically).
    if (oldName = CurrentMapProfileName) {
        profile := BuildMapProfileSaveData()
        SaveMapProfileToIni(newName, profile.ExpectedText, profile.CustomTowers, profile.CustomNumPlacements, profile.Placements, profile.CustomCamera)
        SaveMapAdvStepsFromLV(profile.CustomCamera ? ("MapProfile_" newName) : "General")
    } else {
        CopyIniSection(ConfigFile, "MapProfile_" oldName, "MapProfile_" newName)
    }
    IniDelete ConfigFile, "MapProfile_" oldName
    for idx, n in MapProfileNames {
        if (n = oldName) {
            MapProfileNames[idx] := newName
            break
        }
    }
    RebuildMapProfileDdl()
    if (oldName = CurrentMapProfileName) {
        mapProfileDdl.Text := newName
        CurrentMapProfileName := newName
    } else {
        mapProfileDdl.Text := CurrentMapProfileName
    }
    IniWrite JoinList(MapProfileNames), ConfigFile, "MapProfiles", "List"
    IniWrite CurrentMapProfileName, ConfigFile, "MapProfiles", "Active"
    RebuildDefaultMapDdl()
    LogMsg("Map profile renamed to '" newName "'.")
    return {ok: true, msg: "Map profile renamed to '" newName "'."}
}

RenameMapProfileClick(*) {
    global CurrentMapProfileName
    ib := InputBox("Rename map profile '" CurrentMapProfileName "' to:", "Rename Map Profile", , CurrentMapProfileName)
    if (ib.Result != "OK" || Trim(ib.Value) = "")
        return
    newName := Trim(ib.Value)
    if (newName = CurrentMapProfileName)
        return
    result := RenameMapProfile(CurrentMapProfileName, newName)
    if !result.ok
        MsgBox result.msg
}

; Deletes the explicit map profile without a confirmation dialog. The wrapper retains the legacy
; last-profile guard and Yes/No confirmation, while direct callers receive the same guard result.
DeleteMapProfile(name) {
    global CurrentMapProfileName, mapProfileDdl, MapProfileNames, ConfigFile, Running
    if (MapProfileNames.Length <= 1)
        return {ok: false, msg: "At least one map profile must remain."}
    ; Same reasoning as RenameMapProfile(): no pinned "running map profile" name exists to guard
    ; against specifically, since the active map is detected fresh mid-run - reject deleting ANY
    ; map profile while a run is in progress.
    if Running
        return {ok: false, msg: "Cannot delete a map profile while the macro is running - stop it first."}
    IniDelete ConfigFile, "MapProfile_" name
    newList := []
    for n in MapProfileNames {
        if (n != name)
            newList.Push(n)
    }
    MapProfileNames := newList
    RebuildMapProfileDdl()
    ; Only force the legacy editor to switch away if the profile it was showing is the one that
    ; just got deleted - deleting a different, not-currently-viewed profile must not disturb it.
    if (name = CurrentMapProfileName) {
        CurrentMapProfileName := MapProfileNames[1]
        mapProfileDdl.Text := CurrentMapProfileName
        LoadMapProfile(CurrentMapProfileName)
    } else {
        mapProfileDdl.Text := CurrentMapProfileName
    }
    IniWrite JoinList(MapProfileNames), ConfigFile, "MapProfiles", "List"
    IniWrite CurrentMapProfileName, ConfigFile, "MapProfiles", "Active"
    RebuildDefaultMapDdl()
    LogMsg("Map profile deleted.")
    return {ok: true, msg: "Map profile deleted."}
}

DeleteMapProfileClick(*) {
    global CurrentMapProfileName, MapProfileNames
    if (MapProfileNames.Length <= 1) {
        MsgBox "At least one map profile must remain."
        return
    }
    res := MsgBox("Delete map profile '" CurrentMapProfileName "'?", "Confirm", "YesNo")
    if (res != "Yes")
        return
    result := DeleteMapProfile(CurrentMapProfileName)
    if !result.ok
        MsgBox result.msg
}

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
ShowRegionPreviewFromPct(x1, y1, x2, y2) {
    a := AbsXY(x1, y1)
    b := AbsXY(x2, y2)
    ShowRegionPreview({x: Min(a.x, b.x), y: Min(a.y, b.y), w: Abs(b.x - a.x), h: Abs(b.y - a.y)})
}
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
        try RunWait('taskkill.exe /F /T /PID ' OcrServerPid, , "Hide")
        if ProcessExist(OcrServerPid)
            try ProcessClose(OcrServerPid)
    }
    OcrServerPid := 0
    for f in ["ocr_ready.txt", "ocr_req.txt", "ocr_req.txt.tmp", "ocr_resp.txt", "ocr_resp.txt.tmp", "ocr_stop.txt"]
        try FileDelete DataDir "\" f
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
StepTestOcrClick(*) {
    global stepTypeDdl, stepXEdit, stepYEdit, dragEndXEdit, dragEndYEdit, stepLabelEdit, stepOcrResultText, MapProfileNames
    global stepAdvancedChk, EditingOutcomes
    a := AbsXY(stepXEdit.Value, stepYEdit.Value)
    b := AbsXY(dragEndXEdit.Value, dragEndYEdit.Value)
    rect := {x: Min(a.x, b.x), y: Min(a.y, b.y), w: Abs(b.x - a.x), h: Abs(b.y - a.y)}
    if (rect.w <= 0 || rect.h <= 0) {
        MsgBox "Set both Region1 and Region2 positions first."
        return
    }
    stepOcrResultText.Text := "Reading..."
    text := RunOcrOnRegion(rect.x, rect.y, rect.w, rect.h)
    if (text = "") {
        stepOcrResultText.Text := "(no text recognized)"
        LogMsg("Step OCR test result: (no text recognized)")
        return
    }
    if (stepTypeDdl.Text = "Detect Map") {
        matched := ""
        for name in MapProfileNames {
            expected := Cfg("MapProfile_" name, "ExpectedText", "")
            if (expected != "" && InStr(text, expected)) {
                matched := name
                break
            }
        }
        if (matched = "") {
            for name in MapProfileNames {
                expected := Cfg("MapProfile_" name, "ExpectedText", "")
                if (expected != "" && TextContainsPartialMatch(text, expected, 6)) {
                    matched := name
                    break
                }
            }
        }
        stepOcrResultText.Text := "Recognized: '" text "' -> map: " (matched != "" ? matched : "(none matched)")
    } else if (stepTypeDdl.Text = "Custom Detection" && stepAdvancedChk.Value) {
        matched := ""
        for o in EditingOutcomes {
            if (o.Name != "" && InStr(text, o.Name)) {
                matched := o
                break
            }
        }
        if (matched = "") {
            for o in EditingOutcomes {
                if (o.Name != "" && TextContainsPartialMatch(text, o.Name, 6)) {
                    matched := o
                    break
                }
            }
        }
        stepOcrResultText.Text := "Recognized: '" text "' -> " (matched != "" ? "matches outcome '" matched.Name "' (-> " matched.Screen ")" : "(no outcome matched)")
    } else {
        expected := stepLabelEdit.Value
        isMatch := (expected != "") && (InStr(text, expected) || TextContainsPartialMatch(text, expected, 6))
        stepOcrResultText.Text := "Recognized: '" text "' -> " (isMatch ? "MATCH" : "no match")
    }
    LogMsg("Step OCR test result: '" text "'")
}

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
        expected := Cfg("MapProfile_" name, "ExpectedText", "")
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
DisconnectTestOcrClick(*) {
    global disconnectX1Edit, disconnectY1Edit, disconnectX2Edit, disconnectY2Edit, disconnectTextEdit, disconnectOcrResultText
    a := AbsXY(disconnectX1Edit.Value, disconnectY1Edit.Value)
    b := AbsXY(disconnectX2Edit.Value, disconnectY2Edit.Value)
    rect := {x: Min(a.x, b.x), y: Min(a.y, b.y), w: Abs(b.x - a.x), h: Abs(b.y - a.y)}
    if (rect.w <= 0 || rect.h <= 0) {
        MsgBox "Set both Region1 and Region2 positions first."
        return
    }
    disconnectOcrResultText.Text := "Reading..."
    text := RunOcrOnRegion(rect.x, rect.y, rect.w, rect.h)
    if (text = "") {
        disconnectOcrResultText.Text := "(no text recognized)"
        LogMsg("Disconnect detection OCR test: (no text recognized)")
        return
    }
    expected := disconnectTextEdit.Value
    isMatch := (expected != "") && (InStr(text, expected) || TextContainsPartialMatch(text, expected, 6))
    disconnectOcrResultText.Text := "Recognized: '" text "' -> " (isMatch ? "MATCH" : "no match")
    LogMsg("Disconnect detection OCR test result: '" text "'")
}

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
    section := "MapProfile_" name
    customTowers := Integer(Cfg(section, "CustomTowers", "0"))
    n := customTowers ? Integer(Cfg(section, "CustomNumPlacements", "4")) : Integer(Cfg("General", "NumPlacements", "4"))
    rows := []
    Loop n {
        i := A_Index
        slot := customTowers ? Cfg(section, "CustomSlot" i, "1") : Cfg("General", "Slot" i, "1")
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

; Loads a section's map actions into mapAdvStepsLV (editor UI only).
LoadMapAdvStepsLV(section) {
    global mapAdvStepsLV
    mapAdvStepsLV.Delete()
    for i, s in GetMapAdvSteps(section)
        mapAdvStepsLV.Add("", i, s.Type, s.X, s.Y, s.EndX, s.EndY, s.DragMs)
}

; Saves whatever's currently in mapAdvStepsLV as `section`'s map actions.
SaveMapAdvStepsFromLV(section) {
    global mapAdvStepsLV
    arr := []
    n := mapAdvStepsLV.GetCount()
    Loop n {
        i := A_Index
        arr.Push({Type: mapAdvStepsLV.GetText(i, 2), X: mapAdvStepsLV.GetText(i, 3), Y: mapAdvStepsLV.GetText(i, 4),
            EndX: mapAdvStepsLV.GetText(i, 5), EndY: mapAdvStepsLV.GetText(i, 6), DragMs: mapAdvStepsLV.GetText(i, 7)})
    }
    SaveMapAdvStepsArr(section, arr)
}

; Shows/hides the Drag-only fields (End X/Y, Drag ms) and relabels X (Start X for Drag, Ticks for
; Zoom Out); Y and "Set Position" only make sense for Drag's start point.
UpdateMapAdvEditorLabels(*) {
    global mapAdvTypeDdl, mapAdvXLabel, mapAdvYLabel, mapAdvYEdit, mapAdvPosBtn
    global mapAdvEndXLabel, mapAdvEndXEdit, mapAdvEndYLabel, mapAdvEndYEdit, mapAdvEndPosBtn, mapAdvMsLabel, mapAdvMsEdit
    isDrag := (mapAdvTypeDdl.Text = "Drag")
    for ctrl in [mapAdvEndXLabel, mapAdvEndXEdit, mapAdvEndYLabel, mapAdvEndYEdit, mapAdvEndPosBtn, mapAdvMsLabel, mapAdvMsEdit]
        ctrl.Visible := isDrag
    mapAdvXLabel.Text := isDrag ? "Start X:" : "Ticks:"
    mapAdvYLabel.Visible := isDrag
    mapAdvYEdit.Visible := isDrag
    mapAdvPosBtn.Visible := isDrag
}

MapAdvLoadEditorFromSelection(*) {
    global mapAdvStepsLV, mapAdvTypeDdl, mapAdvXEdit, mapAdvYEdit, mapAdvEndXEdit, mapAdvEndYEdit, mapAdvMsEdit
    row := mapAdvStepsLV.GetNext(0, "Focused")
    if !row
        return
    mapAdvTypeDdl.Text := mapAdvStepsLV.GetText(row, 2)
    mapAdvXEdit.Value := mapAdvStepsLV.GetText(row, 3)
    mapAdvYEdit.Value := mapAdvStepsLV.GetText(row, 4)
    mapAdvEndXEdit.Value := mapAdvStepsLV.GetText(row, 5)
    mapAdvEndYEdit.Value := mapAdvStepsLV.GetText(row, 6)
    mapAdvMsEdit.Value := mapAdvStepsLV.GetText(row, 7)
    UpdateMapAdvEditorLabels()
}

MapAdvAddStepClick(*) {
    global mapAdvStepsLV, mapAdvTypeDdl, mapAdvXEdit, mapAdvYEdit, mapAdvEndXEdit, mapAdvEndYEdit, mapAdvMsEdit
    mapAdvStepsLV.Add("", mapAdvStepsLV.GetCount() + 1, mapAdvTypeDdl.Text, mapAdvXEdit.Value, mapAdvYEdit.Value,
        mapAdvEndXEdit.Value, mapAdvEndYEdit.Value, mapAdvMsEdit.Value)
}

MapAdvUpdateSelectedClick(*) {
    global mapAdvStepsLV, mapAdvTypeDdl, mapAdvXEdit, mapAdvYEdit, mapAdvEndXEdit, mapAdvEndYEdit, mapAdvMsEdit
    row := mapAdvStepsLV.GetNext(0, "Focused")
    if !row {
        LogMsg("No map action selected.")
        return
    }
    mapAdvStepsLV.Modify(row, "", row, mapAdvTypeDdl.Text, mapAdvXEdit.Value, mapAdvYEdit.Value,
        mapAdvEndXEdit.Value, mapAdvEndYEdit.Value, mapAdvMsEdit.Value)
}

MapAdvRemoveSelectedClick(*) {
    global mapAdvStepsLV
    row := mapAdvStepsLV.GetNext(0, "Focused")
    if !row
        return
    mapAdvStepsLV.Delete(row)
    n := mapAdvStepsLV.GetCount()
    Loop n
        mapAdvStepsLV.Modify(A_Index, "", A_Index)
}

MapAdvSwapRows(r1, r2) {
    global mapAdvStepsLV
    t1 := mapAdvStepsLV.GetText(r1, 2), x1 := mapAdvStepsLV.GetText(r1, 3), y1 := mapAdvStepsLV.GetText(r1, 4)
    ex1 := mapAdvStepsLV.GetText(r1, 5), ey1 := mapAdvStepsLV.GetText(r1, 6), dm1 := mapAdvStepsLV.GetText(r1, 7)
    t2 := mapAdvStepsLV.GetText(r2, 2), x2 := mapAdvStepsLV.GetText(r2, 3), y2 := mapAdvStepsLV.GetText(r2, 4)
    ex2 := mapAdvStepsLV.GetText(r2, 5), ey2 := mapAdvStepsLV.GetText(r2, 6), dm2 := mapAdvStepsLV.GetText(r2, 7)
    mapAdvStepsLV.Modify(r1, "", r1, t2, x2, y2, ex2, ey2, dm2)
    mapAdvStepsLV.Modify(r2, "", r2, t1, x1, y1, ex1, ey1, dm1)
}

MapAdvMoveUpClick(*) {
    global mapAdvStepsLV
    row := mapAdvStepsLV.GetNext(0, "Focused")
    if (!row || row = 1)
        return
    MapAdvSwapRows(row, row - 1)
    mapAdvStepsLV.Modify(row - 1, "Focus Select")
}

MapAdvMoveDownClick(*) {
    global mapAdvStepsLV
    row := mapAdvStepsLV.GetNext(0, "Focused")
    n := mapAdvStepsLV.GetCount()
    if (!row || row = n)
        return
    MapAdvSwapRows(row, row + 1)
    mapAdvStepsLV.Modify(row + 1, "Focus Select")
}

; ============================================================
; STEP EDITOR FIELD VISIBILITY (depends on step type)
; ============================================================
; "Logic" steps are the OCR-driven detection types - each has its own region + expected text and
; can jump to another screen on true/false. Everything else is a "Mechanic" step (an action).
IsLogicStepType(t) {
    return (t = "Detect Map" || t = "Round End Detection" || t = "Ingame Detection" || t = "Custom Detection")
}

UpdateStepEditorLabels(*) {
    global stepTypeDdl, stepXLabel, stepYLabel, stepXEdit, stepYEdit, stepPosBtn, stepLabelLbl, OptionSectionControls
    global dragEndXLabel, dragEndXEdit, dragEndYLabel, dragEndYEdit, dragEndPosBtn, dragMsLabel, dragMsEdit
    global stepOcrTestBtn, stepShowRegionBtn, stepOcrResultText, stepOnTrueLbl, stepOnTrueDdl, stepOnFalseLbl, stepOnFalseDdl
    global stepFallbackChk, stepFallbackMaxEdit, stepFallbackScreenLbl, stepFallbackScreenDdl
    global stepAdvancedChk, stepAdvancedConfigBtn
    t := stepTypeDdl.Text
    isDrag := (t = "Drag")
    isLogic := IsLogicStepType(t)
    isCustomDetection := (t = "Custom Detection")
    advancedOn := isCustomDetection && stepAdvancedChk.Value

    ; Challenge options are only relevant while working on an "Option Select" step.
    for ctrl in OptionSectionControls
        ctrl.Visible := (t = "Option Select")

    ; This row is Drag's end point + duration, OR (relabeled below) a Logic step's second region
    ; corner - the duration field only makes sense for Drag.
    for ctrl in [dragEndXLabel, dragEndXEdit, dragEndYLabel, dragEndYEdit]
        ctrl.Visible := (isDrag || isLogic)
    ; A Logic step's OCR region is set by dragging a rectangle (one "Select Region" button fills both
    ; corners at once), so the separate Region2 point-capture button is only for Drag's end point.
    dragEndPosBtn.Visible := isDrag
    stepPosBtn.Text := isLogic ? "Select Region" : "Set Position"
    dragMsLabel.Visible := isDrag
    dragMsEdit.Visible := isDrag
    dragEndXLabel.Text := isLogic ? "Region2 X:" : "End X:"
    dragEndYLabel.Text := isLogic ? "Region2 Y:" : "End Y:"

    ; Logic-only: test the region/expected-text currently entered, and preview the region on screen.
    for ctrl in [stepOcrTestBtn, stepShowRegionBtn, stepOcrResultText]
        ctrl.Visible := isLogic

    ; Every step type can jump to another screen when it finishes. Logic steps get two branches
    ; (On True/On False, based on the OCR result); Mechanic steps get a single unconditional jump
    ; (reusing the same "On True" field/column - e.g. a plain Round End button that just always
    ; goes back to "Ingame" with no detection needed). Advanced Custom Detection replaces both
    ; branches with its own per-outcome screens (Configure Outcomes...), so they're hidden then.
    stepOnTrueLbl.Visible := !advancedOn
    stepOnTrueDdl.Visible := !advancedOn
    stepOnTrueLbl.Text := isLogic ? "On True ->" : "Then Go To ->"
    stepOnFalseLbl.Visible := isLogic && !advancedOn
    stepOnFalseDdl.Visible := isLogic && !advancedOn

    ; Logic-only: the "fallback after N (Repeat) attempts" safety net.
    for ctrl in [stepFallbackChk, stepFallbackMaxEdit, stepFallbackScreenLbl, stepFallbackScreenDdl]
        ctrl.Visible := isLogic

    ; "Advanced Detection" (Custom Detection only): replaces the single fixed True/False branch
    ; with any number of named outcomes - see OpenAdvDetGui/StepAdvancedChkToggled.
    stepAdvancedChk.Visible := isCustomDetection
    stepAdvancedConfigBtn.Visible := advancedOn

    ; The Label field doubles as the OCR "expected text" for Round End/Ingame/Custom Detection
    ; (Detect Map instead matches against every map profile's own expected text, so its Label is
    ; just an optional free description). "Custom Detection" is a freely-nameable version of the
    ; same check - use it for any extra popup/screen you need to detect and click through, without
    ; touching the built-in Map/Round End/Ingame detection logic. Hidden entirely once Advanced
    ; Detection is on, since each outcome carries its own name/expected text instead.
    stepLabelLbl.Text := (t = "Round End Detection" || t = "Ingame Detection" || t = "Custom Detection") ? "Expected Text:" : "Name:"
    stepLabelLbl.Visible := !advancedOn
    stepLabelEdit.Visible := !advancedOn

    if (t = "Zoom Out") {
        stepXLabel.Text := "Ticks:"
        stepXLabel.Visible := true
        stepXEdit.Visible := true
        stepYLabel.Visible := false
        stepYEdit.Visible := false
        stepPosBtn.Visible := false
    } else if (t = "Button Click" || t = "Press Start Button" || t = "Restart Stage Button") {
        stepXLabel.Text := "X:"
        stepXLabel.Visible := true
        stepXEdit.Visible := true
        stepYLabel.Visible := true
        stepYEdit.Visible := true
        stepPosBtn.Visible := true
    } else if (t = "Drag") {
        stepXLabel.Text := "Start X:"
        stepXLabel.Visible := true
        stepXEdit.Visible := true
        stepYLabel.Visible := true
        stepYEdit.Visible := true
        stepPosBtn.Visible := true
    } else if isLogic {
        stepXLabel.Text := "Region1 X:"
        stepXLabel.Visible := true
        stepXEdit.Visible := true
        stepYLabel.Visible := true
        stepYEdit.Visible := true
        stepPosBtn.Visible := true
    } else {
        ; Start, Option Select, Camera Setup, Place Towers, Wait -> no coordinates needed here
        stepXLabel.Visible := false
        stepXEdit.Visible := false
        stepYLabel.Visible := false
        stepYEdit.Visible := false
        stepPosBtn.Visible := false
    }
    stepYLabel.Text := (t = "Drag") ? "Start Y:" : (isLogic ? "Region1 Y:" : "Y:")
}

; Runs only when the user manually picks a type from the dropdown - this always starts authoring a
; FRESH step of that type: every other field is cleared to its default (and any selected list row
; is deselected), so a new step never inherits the settings of the one that was last clicked. Named
; button steps get sensible default coordinates prefilled. Not called when loading an existing step
; (LoadEditorFromSelection calls UpdateStepEditorLabels directly), so editing never clobbers a step.
StepTypeChangedByUser(*) {
    global stepTypeDdl, stepXEdit, stepYEdit
    t := stepTypeDdl.Text
    ClearStepEditorFields()
    if (t = "Press Start Button") {
        stepXEdit.Value := "733"
        stepYEdit.Value := "555"
    } else if (t = "Restart Stage Button") {
        stepXEdit.Value := "400"
        stepYEdit.Value := "620"
    }
    UpdateStepEditorLabels()
}

; Fires when the "Advanced Detection" checkbox itself is clicked. Seeds 2 default outcomes
; ("True"/"False", both "(continue)") the first time it's turned on for a step that doesn't have
; any yet - mirroring the normal True/False branch it replaces - so "Configure Outcomes..." (or
; committing the step right away) never starts from an empty, unusable list.
StepAdvancedChkToggled(*) {
    global stepAdvancedChk, EditingOutcomes
    if (stepAdvancedChk.Value && EditingOutcomes.Length = 0) {
        EditingOutcomes.Push({Name: "True", Screen: "(continue)"})
        EditingOutcomes.Push({Name: "False", Screen: "(continue)"})
    }
    UpdateStepEditorLabels()
}

; ============================================================
; POSITION CAPTURE (F8) - with a red dot marker that follows the mouse
; ============================================================
GetMarkerSize() {
    size := SafeInt(Cfg("General", "MarkerSize", "4"), 4)
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

StartCapture(xCtrl, yCtrl, *) {
    global CaptureTarget, CaptureXCtrl, CaptureYCtrl, MyGui, MarkerGui
    CaptureXCtrl := xCtrl
    CaptureYCtrl := yCtrl
    CaptureTarget := "active"
    MyGui.Hide()
    try MarkerGui.Show("NoActivate")
    SetTimer UpdateMarkerPos, 30
    ToolTip "Move the mouse to the target position and press F8. Escape = Cancel."
}

; The Python GUI has no live AHK edit control to receive a captured point, so it identifies the
; destination by field ID and consumes this one-shot result file instead.
BeginFieldCapture(fieldId) {
    global FieldCaptureId, FieldCaptureRestoreGui, MyGui, MarkerGui, DataDir
    ; A previous capture's result must never satisfy a newly issued request.
    try FileDelete DataDir "\local_capture_result.txt"
    FieldCaptureId := fieldId
    ; Unlike StartCapture (only ever reachable via a button ON MyGui, so MyGui is guaranteed
    ; visible when it fires), a bridge-triggered capture can start at any time - including
    ; headless, with MyGui never shown. Only hide-then-restore it if it was actually visible to
    ; begin with, so this never pops the legacy window on screen for a caller that never had it open.
    FieldCaptureRestoreGui := DllCall("IsWindowVisible", "Ptr", MyGui.Hwnd)
    if FieldCaptureRestoreGui
        MyGui.Hide()
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
    global CaptureTarget, CaptureXCtrl, CaptureYCtrl, MyGui, MarkerGui
    global FieldCaptureId, FieldCaptureRestoreGui
    if (FieldCaptureId != "") {
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
        if FieldCaptureRestoreGui
            MyGui.Show()
        return
    }
    if (CaptureTarget != "active")
        return
    MouseGetPos &mx, &my
    ; Store the captured point as a percentage of the opening, not a raw screen pixel (see the
    ; window-relative coordinates section) - so it follows the window if the opening moves/resizes.
    CaptureXCtrl.Value := PctXFromAbs(mx)
    CaptureYCtrl.Value := PctYFromAbs(my)
    CaptureTarget := ""
    SetTimer UpdateMarkerPos, 0
    size := GetMarkerSize()
    half := size // 2
    try MarkerGui.Move(mx - half, my - half, size, size)
    SetTimer HideMarker, -2000
    ToolTip()
    MyGui.Show()
}

; ============================================================
; OCR REGION CAPTURE (snipping-tool style: drag a red rectangle)
; ============================================================
; Instead of setting the two opposite corners of an OCR region with two separate F8 point captures,
; this lets you drag a single rectangle (like the Windows Snipping Tool): the app windows hide, the
; screen dims, and a red rectangle follows the mouse while the left button is held. On release, the
; rectangle's corners are written (as window-relative percentages) to its GUI controls or Python field IDs.
StartRegionCapture(x1Ctrl, y1Ctrl, x2Ctrl, y2Ctrl) {
    global RegionCapActive, RegionCapPhase, RegionCapTargets, RegionCapRestore
    global RegionDimGui, RegionBandGuis, MyGui, EditGui, OptionAvailGui, MapAdvGui
    if RegionCapActive
        return
    RegionCapTargets := [x1Ctrl, y1Ctrl, x2Ctrl, y2Ctrl]
    SetupRegionCapture()
}

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
    global RegionCapActive, RegionCapPhase, RegionCapTargets, RegionCapRestore
    global RegionDimGui, RegionBandGuis, MyGui, EditGui, OptionAvailGui, MapAdvGui

    ; Hide any of the app's own windows that are open, so they don't block the view of the game.
    RegionCapRestore := []
    for g in [MyGui, EditGui, MapAdvGui, OptionAvailGui] {
        if (g != "" && DllCall("IsWindowVisible", "Ptr", g.Hwnd))
            RegionCapRestore.Push(g), g.Hide()
    }

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
StepPosBtnClick() {
    global stepTypeDdl, stepXEdit, stepYEdit, dragEndXEdit, dragEndYEdit
    if IsLogicStepType(stepTypeDdl.Text)
        StartRegionCapture(stepXEdit, stepYEdit, dragEndXEdit, dragEndYEdit)
    else
        StartCapture(stepXEdit, stepYEdit)
}

; ============================================================
; GAME WINDOW / PROCESS LIST
; ============================================================
RefreshProcessList(*) {
    global gameProcessDdl, ConfigFile
    candidates := EnumerateGameProcessCandidates()
    list := []
    for candidate in candidates
        list.Push(candidate.Title " | " candidate.Proc)
    gameProcessDdl.Delete()
    gameProcessDdl.Add(list)

    savedProc := Cfg("General", "GameProcess", "")
    if (savedProc != "") {
        for candidate in candidates {
            if (candidate.Proc = savedProc) {
                gameProcessDdl.Text := candidate.Title " | " candidate.Proc
                break
            }
        }
    }
}

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
GetSelectedGameProcess() {
    global gameProcessDdl
    t := gameProcessDdl.Text
    if (t = "")
        return ""
    parts := StrSplit(t, " | ")
    return parts.Length >= 2 ? parts[2] : ""
}

; The persisted process name the engine should actually act on (config.ini, kept current by
; whichever explicit Save action - native GUI or the local IPC bridge's SAVE_GENERAL - last ran).
; Deliberately separate from GetSelectedGameProcess(): that one reads a native GUI control the
; engine must not depend on, since a later phase deletes it.
ConfiguredGameProcess() {
    return Cfg("General", "GameProcess", "")
}

; ============================================================
; FULLSCREEN GRAY OVERLAY WITH A RECTANGULAR OPENING
; Built from 4 borderless always-on-top bars forming a frame around the opening,
; instead of punching an actual hole in one window (simpler and more reliable).
; ============================================================
GetHoleRect() {
    return {x: SafeInt(Cfg("General", "HoleX", 0)), y: SafeInt(Cfg("General", "HoleY", 0)),
        w: SafeInt(Cfg("General", "HoleW", 0)), h: SafeInt(Cfg("General", "HoleH", 0))}
}

CreateOverlay() {
    global OverlayGuis, OverlayVisible, LogGui, LogEdit, LogLines, StatsGui
    global StatsCycleText, StatsMapText, StatsScreenText, StatsStepText
    global StatsStepRepeatText, StatsStartRepeatText, StatsVictoryText, StatsDefeatText
    global StatsLastVals
    global ScreenCountGui, ScreenCountEdit
    if OverlayVisible
        return
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

    ; Log panel + Screen Run Counts panel: together fill a column to the right of the game window,
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
        screenCountH := 320
        screenCountGap := 10
        showScreenCounts := (columnH - screenCountH - screenCountGap) >= 150
        logH := showScreenCounts ? (columnH - screenCountH - screenCountGap) : columnH

        LogGui := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x08000000")
        LogGui.BackColor := "000000"
        LogGui.SetFont("s9 cWhite", "Consolas")
        LogEdit := LogGui.AddEdit("x" margin " y" margin " w" (panelW - margin * 2) " h" (logH - margin * 2)
            . " ReadOnly VScroll Background000000 cWhite")
        LogGui.Show("x" panelX " y" hole.y " w" panelW " h" logH " NoActivate")
        ; Seed the panel with whatever's already in the log so far, instead of starting blank.
        RenderLogPanel()

        if showScreenCounts {
            ScreenCountGui := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x08000000")
            ScreenCountGui.BackColor := "000000"
            ScreenCountGui.SetFont("s9 cWhite", "Consolas")
            ScreenCountEdit := ScreenCountGui.AddEdit("x" margin " y" margin " w" (panelW - margin * 2) " h" (screenCountH - margin * 2)
                . " ReadOnly VScroll Background000000 cWhite")
            ScreenCountGui.Show("x" panelX " y" (hole.y + logH + screenCountGap) " w" panelW " h" screenCountH " NoActivate")
            RenderScreenCountPanel()
        } else {
            ScreenCountGui := ""
            ScreenCountEdit := ""
        }
    } else {
        LogGui := ""
        LogEdit := ""
        ScreenCountGui := ""
        ScreenCountEdit := ""
    }

    ; Application Stats panel: a black bar BELOW the game window, spanning just its width (the
    ; Log/Screen Run Counts column to the right now runs down alongside it instead of sharing this
    ; row), placed in the bottom gray bar.
    statsAreaY := hole.y + hole.h
    statsAreaH := screenH - statsAreaY
    if (statsAreaH > 140) {
        statsMargin := 10
        statsGapTop := panelGap      ; same gap as the log/screen-count column's top-side inset
        statsGapBottom := bottomMargin   ; same bottom margin the log/screen-count column ends at
        statsX := hole.x
        statsW := hole.w
        statsH := Max(140, statsAreaH - statsGapTop - statsGapBottom)
        statsY := statsAreaY + statsGapTop

        StatsGui := Gui("+AlwaysOnTop -Caption +ToolWindow +E0x08000000")
        StatsGui.BackColor := "000000"

        StatsGui.SetFont("s13 cWhite Bold", "Segoe UI")
        StatsGui.AddText("x" statsMargin " y" statsMargin " w" (statsW - statsMargin * 2 - 80) " h26", "Application Stats")
        StatsGui.SetFont("s9 cBlack Norm", "Segoe UI")
        statsCopyBtn := StatsGui.AddButton("x" (statsW - statsMargin - 70) " y" statsMargin " w70 h22", "Copy")
        statsCopyBtn.OnEvent("Click", (*) => CopyStatsClick())

        ; Two rows of 4 evenly spaced columns across the full width - label on top, big value
        ; underneath. Row 1 is this run's live state; Row 2 is the counters (Step/Screen Repeat
        ; reset every run, Start Repeat/Victory/Defeat are lifetime counts for the whole session).
        colW := Integer((statsW - statsMargin * 2) / 4)
        row1Labels := ["Screen Repetition Count", "Current Map", "Current Screen", "Current Step"]
        row2Labels := ["Step Repetition Count", "Start Repetition Count", "Victory Count", "Defeat Count"]
        rowY1 := statsMargin + 44
        rowY2 := rowY1 + 54
        row1Texts := []
        row2Texts := []
        loop 4 {
            colX := statsMargin + (A_Index - 1) * colW
            StatsGui.SetFont("s9 cWhite Norm", "Segoe UI")
            StatsGui.AddText("x" colX " y" rowY1 " w" (colW - 10) " h16", row1Labels[A_Index])
            StatsGui.SetFont("s14 cWhite Bold", "Segoe UI")
            row1Texts.Push(StatsGui.AddText("x" colX " y" (rowY1 + 20) " w" (colW - 10) " h26", "-"))

            StatsGui.SetFont("s9 cWhite Norm", "Segoe UI")
            StatsGui.AddText("x" colX " y" rowY2 " w" (colW - 10) " h16", row2Labels[A_Index])
            StatsGui.SetFont("s14 cWhite Bold", "Segoe UI")
            row2Texts.Push(StatsGui.AddText("x" colX " y" (rowY2 + 20) " w" (colW - 10) " h26", "-"))
        }
        StatsCycleText := row1Texts[1]
        StatsMapText := row1Texts[2]
        StatsScreenText := row1Texts[3]
        StatsStepText := row1Texts[4]
        StatsStepRepeatText := row2Texts[1]
        StatsStartRepeatText := row2Texts[2]
        StatsVictoryText := row2Texts[3]
        StatsDefeatText := row2Texts[4]
        StatsLastVals := Map()   ; fresh controls (all showing "-") - clear the change-cache so the

        StatsGui.Show("x" statsX " y" statsY " w" statsW " h" statsH " NoActivate")
        RenderStatsPanel()       ; ...first render populates every row
    } else {
        StatsGui := ""
        StatsCycleText := ""
        StatsMapText := ""
        StatsScreenText := ""
        StatsStepText := ""
        StatsStepRepeatText := ""
        StatsStartRepeatText := ""
        StatsVictoryText := ""
        StatsDefeatText := ""
    }

    OverlayVisible := true
    LogMsg("Overlay opened.")
}

CloseOverlay(*) {
    global OverlayGuis, OverlayVisible, LockedProcess, LogGui, LogEdit, StatsGui
    global StatsCycleText, StatsMapText, StatsScreenText, StatsStepText
    global StatsStepRepeatText, StatsStartRepeatText, StatsVictoryText, StatsDefeatText
    global ScreenCountGui, ScreenCountEdit
    SetTimer EnforceWindowLock, 0
    LockedProcess := ""
    for g in OverlayGuis {
        try g.Destroy()
    }
    OverlayGuis := []
    if (LogGui != "") {
        try LogGui.Destroy()
    }
    LogGui := ""
    LogEdit := ""
    if (ScreenCountGui != "") {
        try ScreenCountGui.Destroy()
    }
    ScreenCountGui := ""
    ScreenCountEdit := ""
    if (StatsGui != "") {
        try StatsGui.Destroy()
    }
    StatsGui := ""
    StatsCycleText := ""
    StatsMapText := ""
    StatsScreenText := ""
    StatsStepText := ""
    StatsStepRepeatText := ""
    StatsStartRepeatText := ""
    StatsVictoryText := ""
    StatsDefeatText := ""
    OverlayVisible := false
    LogMsg("Overlay closed. Window lock released.")
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
    winCrit := "ahk_exe " LockedProcess
    hwnd := WinExist(winCrit)
    if !hwnd
        return
    hole := GetHoleRect()
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
; configured "disconnected" text; if found, clicks the Reconnect Button position and asks
; StartMacro() to restart the current preset from the beginning (via DisconnectRestartPending) -
; the same way Escape already stops the run asynchronously mid-step, just auto-resuming afterward
; instead of staying stopped. Uses its own OCR output file (ocr_result_disconnect.txt) so a scan
; firing here never races with a step's own OCR call (e.g. Round End Detection) that might be in
; progress on the main thread at the same moment.
CheckDisconnectTick() {
    global Running, DisconnectCheckBusy, DisconnectLastCheckTick, DisconnectRestartPending, OcrBusy

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

    ReactivateGameWindow()
    LogMsg("Disconnect detected -> clicking Reconnect and restarting from the beginning.")
    rc := AbsXY(Cfg("General", "DisconnectReconnectX", 0), Cfg("General", "DisconnectReconnectY", 0))
    ActClick(rc.x, rc.y)
    Running := false
    DisconnectRestartPending := true
    DisconnectCheckBusy := false
}
SetTimer(CheckDisconnectTick, 500)

; Ensures the overlay is showing, then moves the game window into the opening
; and locks it there so it can't be dragged or resized out of place by accident.
ForceGameWindow() {
    global LockedProcess
    proc := ConfiguredGameProcess()
    if (proc = "")
        return true  ; no process selected -> feature not in use, not an error

    winCrit := "ahk_exe " proc
    if !WinExist(winCrit) {
        LogMsg("WARNING: game window not found (" proc ").")
        return false
    }

    CreateOverlay()
    hole := GetHoleRect()

    try WinRestore winCrit
    WinActivate winCrit
    Sleep 200
    hwnd := WinExist(winCrit)
    if hwnd {
        DisableRoundedCorners(hwnd)
        MoveWindowToVisibleRect(hwnd, hole.x, hole.y, hole.w, hole.h)
    }

    LockedProcess := proc
    SetTimer EnforceWindowLock, 500

    LogMsg("Game window positioned and locked (" proc ").")
    return true
}

PlacementModeClick(*) {
    ClearLog()
    ok := ForceGameWindow()
    if ok
        LogMsg("Placement Mode: window positioned. Use the Set Position buttons to record coordinates.")
    else
        LogMsg("Placement Mode: could not position the game window.")
}

F7::PlacementModeClick()

; ============================================================
; PAUSE / STOP
; ============================================================
F9:: {
    global Paused
    Paused := !Paused
    LogMsg(Paused ? "Paused." : "Resumed.")
}

; Cancels a pending Python field-id point capture (see BeginFieldCapture), publishing a
; cancelled result and restoring MarkerGui/MyGui exactly like the Escape hotkey always has.
; Pulled out of Escape:: so a non-hotkey caller (the local bridge's CANCEL_CAPTURE verb) can
; trigger the identical cleanup instead of duplicating it - mirrors CancelRegionCapture().
CancelFieldCapture() {
    global FieldCaptureId, FieldCaptureRestoreGui, MyGui, MarkerGui
    WriteFieldCaptureResult(FieldCaptureId, true)
    FieldCaptureId := ""
    SetTimer UpdateMarkerPos, 0
    try MarkerGui.Hide()
    ToolTip()
    if FieldCaptureRestoreGui
        MyGui.Show()
    LogMsg("Position capture cancelled.")
}

Escape:: {
    global CaptureTarget, Running, MyGui, OverlayVisible, MarkerGui, RegionCapActive
    global PendingPresetSwitch, PresetSwitchRestartPending, StopRequested
    global FieldCaptureId, FieldCaptureRestoreGui
    if RegionCapActive {
        CancelRegionCapture()
        return
    }
    if (FieldCaptureId != "") {
        CancelFieldCapture()
        return
    }
    if (CaptureTarget = "active") {
        CaptureTarget := ""
        SetTimer UpdateMarkerPos, 0
        try MarkerGui.Hide()
        ToolTip()
        MyGui.Show()
        LogMsg("Position capture cancelled.")
        return
    }
    if OverlayVisible
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
; called whenever a fresh run starts (macro or Placement Mode) so the panel only shows this run.
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

; Refreshes the "Screen Run Counts" panel - one line per screen in the currently running preset,
; in preset order, showing how many times each has run so far THIS run (see ScreenRunCounts;
; resets every MainLoop() call, same scope as ScreenRepeatCount/StepRepeatCount). Safe to call even
; when the overlay/panel doesn't exist, or before PresetScreens has been built yet.
RenderScreenCountPanel() {
    global ScreenCountEdit, PresetScreens, ScreenRunCounts
    if (ScreenCountEdit = "")
        return
    try {
        display := ""
        for scr in PresetScreens
            display .= scr.Name ": " (ScreenRunCounts.Has(scr.Name) ? ScreenRunCounts[scr.Name] : 0) "`n"
        ScreenCountEdit.Value := display
    }
}

; Puts the Application Stats panel's current values on the clipboard - same rationale as needed
; anywhere in this NOACTIVATE overlay (see CreateOverlay): its controls can't get real keyboard
; focus, so click-to-select + Ctrl+C doesn't work reliably; a button click does.
CopyStatsClick(*) {
    global ScreenRepeatCount, LastDetectedMap, RunningScreenName, RunningStepDescription
    global StepRepeatCount, StartRepeatCount, VictoryCount, DefeatCount
    text := "Screen Repetition Count: " ScreenRepeatCount "`n"
        . "Current Map: " (LastDetectedMap != "" ? LastDetectedMap : "(none)") "`n"
        . "Current Screen: " (RunningScreenName != "" ? RunningScreenName : "-") "`n"
        . "Current Step: " (RunningStepDescription != "" ? RunningStepDescription : "-") "`n"
        . "Step Repetition Count: " StepRepeatCount "`n"
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
    global StatsCycleText, StatsMapText, StatsScreenText, StatsStepText
    global StatsStepRepeatText, StatsStartRepeatText, StatsVictoryText, StatsDefeatText
    global ScreenRepeatCount, LastDetectedMap, RunningScreenName, RunningStepDescription
    global StepRepeatCount, StartRepeatCount, VictoryCount, DefeatCount
    if (StatsCycleText = "")
        return
    SetStatText(StatsCycleText, "cycle", ScreenRepeatCount)
    SetStatText(StatsMapText, "map", LastDetectedMap != "" ? LastDetectedMap : "(none)")
    SetStatText(StatsScreenText, "screen", RunningScreenName != "" ? RunningScreenName : "-")
    SetStatText(StatsStepText, "step", RunningStepDescription != "" ? RunningStepDescription : "-")
    SetStatText(StatsStepRepeatText, "steprep", StepRepeatCount)
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
BuildGeneralSaveData() {
    global roundWaitEdit, clickDelayEdit, placeTowerDelayEdit, maxRoundsEdit
    global holeXEdit, holeYEdit, holeWEdit, holeHEdit, markerSizeEdit, numPlaceDdl, GeneralSlotDdls
    global afterPlaceClickChk, afterPlaceXEdit, afterPlaceYEdit
    global disconnectEnabledChk, disconnectX1Edit, disconnectY1Edit, disconnectX2Edit, disconnectY2Edit
    global disconnectTextEdit, disconnectReconnectXEdit, disconnectReconnectYEdit, disconnectIntervalEdit, remoteBridgeChk
    slots := []
    for ddl in GeneralSlotDdls
        slots.Push(ddl.Text)
    return {RoundWaitSeconds: roundWaitEdit.Value, ClickDelayMs: clickDelayEdit.Value,
        PlaceTowerDelayMs: placeTowerDelayEdit.Value, AfterPlaceClick: afterPlaceClickChk.Value,
        AfterPlaceClickX: afterPlaceXEdit.Value, AfterPlaceClickY: afterPlaceYEdit.Value,
        MaxRounds: maxRoundsEdit.Value, MarkerSize: markerSizeEdit.Value, NumPlacements: numPlaceDdl.Text,
        Slots: slots, GameProcess: GetSelectedGameProcess(), HoleX: holeXEdit.Value, HoleY: holeYEdit.Value,
        HoleW: holeWEdit.Value, HoleH: holeHEdit.Value, DisconnectEnabled: disconnectEnabledChk.Value,
        DisconnectX1: disconnectX1Edit.Value, DisconnectY1: disconnectY1Edit.Value,
        DisconnectX2: disconnectX2Edit.Value, DisconnectY2: disconnectY2Edit.Value,
        DisconnectText: disconnectTextEdit.Value, DisconnectReconnectX: disconnectReconnectXEdit.Value,
        DisconnectReconnectY: disconnectReconnectYEdit.Value, DisconnectIntervalSec: disconnectIntervalEdit.Value,
        RemoteBridgeEnabled: remoteBridgeChk.Value}
}

; Writes exactly the flat [General] fields from a plain data object. Preset/map-profile sections,
; list/active pointers, and backup policy remain the responsibility of SaveConfig().
SaveGeneralFromData(fields) {
    global ConfigFile
    IniWrite fields.RoundWaitSeconds, ConfigFile, "General", "RoundWaitSeconds"
    IniWrite fields.ClickDelayMs, ConfigFile, "General", "ClickDelayMs"
    IniWrite fields.PlaceTowerDelayMs, ConfigFile, "General", "PlaceTowerDelayMs"
    IniWrite fields.AfterPlaceClick, ConfigFile, "General", "AfterPlaceClick"
    IniWrite fields.AfterPlaceClickX, ConfigFile, "General", "AfterPlaceClickX"
    IniWrite fields.AfterPlaceClickY, ConfigFile, "General", "AfterPlaceClickY"
    IniWrite fields.MaxRounds, ConfigFile, "General", "MaxRounds"
    IniWrite fields.MarkerSize, ConfigFile, "General", "MarkerSize"
    IniWrite fields.NumPlacements, ConfigFile, "General", "NumPlacements"
    for i, slot in fields.Slots
        IniWrite slot, ConfigFile, "General", "Slot" i
    IniWrite fields.GameProcess, ConfigFile, "General", "GameProcess"
    IniWrite fields.HoleX, ConfigFile, "General", "HoleX"
    IniWrite fields.HoleY, ConfigFile, "General", "HoleY"
    IniWrite fields.HoleW, ConfigFile, "General", "HoleW"
    IniWrite fields.HoleH, ConfigFile, "General", "HoleH"
    IniWrite fields.DisconnectEnabled, ConfigFile, "General", "DisconnectEnabled"
    IniWrite fields.DisconnectX1, ConfigFile, "General", "DisconnectX1"
    IniWrite fields.DisconnectY1, ConfigFile, "General", "DisconnectY1"
    IniWrite fields.DisconnectX2, ConfigFile, "General", "DisconnectX2"
    IniWrite fields.DisconnectY2, ConfigFile, "General", "DisconnectY2"
    IniWrite fields.DisconnectText, ConfigFile, "General", "DisconnectText"
    IniWrite fields.DisconnectReconnectX, ConfigFile, "General", "DisconnectReconnectX"
    IniWrite fields.DisconnectReconnectY, ConfigFile, "General", "DisconnectReconnectY"
    IniWrite fields.DisconnectIntervalSec, ConfigFile, "General", "DisconnectIntervalSec"
    IniWrite fields.RemoteBridgeEnabled, ConfigFile, "General", "RemoteBridgeEnabled"
}

SaveConfig(*) {
    global ConfigFile, CurrentPresetName, PresetNames, ActivePresetName, CurrentMapProfileName, MapProfileNames

    BackupConfig()   ; snapshot the last-good config before overwriting it
    SaveGeneralFromData(BuildGeneralSaveData())

    ; Challenge options and the default-map fallback are saved per-preset inside
    ; SavePresetToIni() below (they live in [Preset_<name>], not [General]).
    if (CurrentPresetName != "")
        SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
    IniWrite JoinList(PresetNames), ConfigFile, "Presets", "List"
    ; "Active" is the preset that RUNS on Start (set via "Set as Active"), not the one being viewed.
    IniWrite (ActivePresetName != "" ? ActivePresetName : CurrentPresetName), ConfigFile, "Presets", "Active"

    if (CurrentMapProfileName != "") {
        profile := BuildMapProfileSaveData()
        SaveMapProfileToIni(CurrentMapProfileName, profile.ExpectedText, profile.CustomTowers, profile.CustomNumPlacements, profile.Placements, profile.CustomCamera)
        SaveMapAdvStepsFromLV(profile.CustomCamera ? ("MapProfile_" CurrentMapProfileName) : "General")
    }
    IniWrite JoinList(MapProfileNames), ConfigFile, "MapProfiles", "List"
    IniWrite CurrentMapProfileName, ConfigFile, "MapProfiles", "Active"
}

; ============================================================
; PRESET MANAGEMENT
; ============================================================
; Reads a preset's ordered list of screen names.
GetPresetScreenNames(name) {
    section := "Preset_" name
    n := Integer(Cfg(section, "ScreenCount", "0"))
    arr := []
    Loop n
        arr.Push(Cfg(section, "Screen" A_Index "Name", "Screen " A_Index))
    return arr
}

; Position (1-based) of `screenName` in `name`'s screen list, or 0 if not found.
ScreenIndexByName(name, screenName) {
    for i, n in GetPresetScreenNames(name) {
        if (n = screenName)
            return i
    }
    return 0
}

; Reads one screen's steps by index (used by both the editor and the running macro).
BuildScreenStepsFromIni(name, screenIdx) {
    section := "Preset_" name
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

BuildScreenStepsFromIniByName(name, screenName) {
    idx := ScreenIndexByName(name, screenName)
    if !idx
        return []
    return BuildScreenStepsFromIni(name, idx)
}

; Writes one screen's full data (name + steps) at the given index. Used for saves, reordering,
; and rebuilding after a delete.
WriteScreenSteps(name, idx, screenName, steps) {
    global ConfigFile
    section := "Preset_" name
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

; Loads a preset's screen list into screenDdl and shows the first screen's steps. Seeds a single
; empty "Screen 1" if the preset somehow has none yet.
LoadPresetScreens(name) {
    global screenDdl, CurrentScreenName, ConfigFile
    names := GetPresetScreenNames(name)
    if (names.Length = 0) {
        names := ["Screen 1"]
        IniWrite 1, ConfigFile, "Preset_" name, "ScreenCount"
        IniWrite "Screen 1", ConfigFile, "Preset_" name, "Screen1Name"
        IniWrite 0, ConfigFile, "Preset_" name, "Screen1StepCount"
    }
    screenDdl.Delete()
    screenDdl.Add(names)
    CurrentScreenName := names[1]
    screenDdl.Text := CurrentScreenName
    LoadScreenSteps(name, CurrentScreenName)
}

; Repopulates screenDdl's item list (e.g. after a screen is added/renamed/removed/reordered)
; without touching stepsLV.
RefreshScreenDdlItems(name, selectName) {
    global screenDdl
    screenDdl.Delete()
    screenDdl.Add(GetPresetScreenNames(name))
    screenDdl.Text := selectName
}

; Loads one screen's steps into stepsLV (editor UI only), and refreshes the On True/On False
; jump-target dropdowns to match this preset's current screen list.
LoadScreenSteps(name, screenName) {
    global StepRows
    StepRows := BuildScreenStepsFromIniByName(name, screenName)
    RenderStepsLV()
    RefreshJumpTargetDdls(name)
}

; Saves the explicit plain `steps` array as the given screen's steps. GUI callers pass StepRows;
; non-GUI callers can save another screen without reading the editor's current ListView backing state.
SaveScreenToIni(name, screenName, steps) {
    global ConfigFile
    idx := ScreenIndexByName(name, screenName)
    if !idx
        return
    section := "Preset_" name
    IniWrite steps.Length, ConfigFile, section, "Screen" idx "StepCount"
    for i, s in steps {
        IniWrite s.Type, ConfigFile, section, "Screen" idx "Step" i "Type"
        IniWrite s.Label, ConfigFile, section, "Screen" idx "Step" i "Label"
        IniWrite s.X, ConfigFile, section, "Screen" idx "Step" i "X"
        IniWrite s.Y, ConfigFile, section, "Screen" idx "Step" i "Y"
        IniWrite s.EndX, ConfigFile, section, "Screen" idx "Step" i "EndX"
        IniWrite s.EndY, ConfigFile, section, "Screen" idx "Step" i "EndY"
        IniWrite s.DragMs, ConfigFile, section, "Screen" idx "Step" i "DragMs"
        IniWrite (s.OncePerCycle ? 1 : 0), ConfigFile, section, "Screen" idx "Step" i "OncePerCycle"
        IniWrite s.OnTrueScreen, ConfigFile, section, "Screen" idx "Step" i "OnTrueScreen"
        IniWrite s.OnFalseScreen, ConfigFile, section, "Screen" idx "Step" i "OnFalseScreen"
        IniWrite s.Seconds, ConfigFile, section, "Screen" idx "Step" i "Seconds"
        IniWrite (s.FallbackEnabled ? 1 : 0), ConfigFile, section, "Screen" idx "Step" i "FallbackEnabled"
        IniWrite s.FallbackMaxAttempts, ConfigFile, section, "Screen" idx "Step" i "FallbackMaxAttempts"
        IniWrite s.FallbackScreen, ConfigFile, section, "Screen" idx "Step" i "FallbackScreen"
        IniWrite (s.Advanced ? 1 : 0), ConfigFile, section, "Screen" idx "Step" i "Advanced"
        IniWrite s.OutcomesRaw, ConfigFile, section, "Screen" idx "Step" i "Outcomes"
    }
}

; Selects a DropDownList entry by its text, guarding against AHK v2's "Invalid value" error that
; is thrown when the requested value is no longer present in the (freshly rebuilt) `items` list -
; e.g. the previously selected screen was renamed or deleted. Falls back to `default` in that case.
SelectDdlText(ctrl, items, value, default) {
    for it in items {
        if (it = value) {
            ctrl.Text := value
            return
        }
    }
    ctrl.Text := default
}

; Repopulates the step editor's On True/On False dropdowns (plus the Option Select Fallback
; Screen dropdown) with every screen name in `name`'s preset, preserving each one's current
; selection where still valid. Called whenever the screen list changes (add/rename/delete/move)
; and every time the visible screen switches, so it must NOT clobber a not-yet-saved selection.
RefreshJumpTargetDdls(name) {
    global stepOnTrueDdl, stepOnFalseDdl, fallbackScreenDdl, stepFallbackScreenDdl
    ; "(Repeat)" is a pseudo-screen, not an actual one - handled specially in RunSteps instead of
    ; being resolved as a screen jump: it re-runs this exact step again (honoring its own "Wait
    ; After" as the pause between attempts) instead of moving to the next step or another screen.
    items := ["(continue)", "(Repeat)"]
    for n in GetPresetScreenNames(name)
        items.Push(n)
    curTrue := stepOnTrueDdl.Text
    curFalse := stepOnFalseDdl.Text
    stepOnTrueDdl.Delete()
    stepOnTrueDdl.Add(items)
    stepOnFalseDdl.Delete()
    stepOnFalseDdl.Add(items)
    SelectDdlText(stepOnTrueDdl, items, curTrue, "(continue)")
    SelectDdlText(stepOnFalseDdl, items, curFalse, "(continue)")

    ; "(Stop Macro)" is a pseudo-screen, not an actual one - handled specially in RunSteps'
    ; "Option Select" case (and the per-step Logic fallback below) instead of being resolved as a
    ; jump target.
    fbItems := ["(none)", "(Stop Macro)"]
    for n in GetPresetScreenNames(name)
        fbItems.Push(n)
    curFallback := fallbackScreenDdl.Text
    fallbackScreenDdl.Delete()
    fallbackScreenDdl.Add(fbItems)
    SelectDdlText(fallbackScreenDdl, fbItems, curFallback, "(none)")

    ; Same item list, reused for the per-step Logic "Fallback after N attempts" screen dropdown.
    curStepFallback := stepFallbackScreenDdl.Text
    stepFallbackScreenDdl.Delete()
    stepFallbackScreenDdl.Add(fbItems)
    SelectDdlText(stepFallbackScreenDdl, fbItems, curStepFallback, "(none)")
}

; Switches which screen's steps are shown in stepsLV, saving the screen being left first.
ScreenChanged(*) {
    global CurrentPresetName, CurrentScreenName, screenDdl, StepRows
    SaveScreenToIni(CurrentPresetName, CurrentScreenName, StepRows)
    CurrentScreenName := screenDdl.Text
    LoadScreenSteps(CurrentPresetName, CurrentScreenName)
}

; Creates a screen in the explicit preset. The ini mutation always targets `presetName`; visible
; editor state is changed only when that preset is the one currently being edited, so a future
; non-interactive caller cannot make an unrelated preset take over the legacy screen editor.
CreateScreen(presetName, screenName) {
    global CurrentPresetName, CurrentScreenName, screenDdl, ConfigFile, StepRows
    screenName := Trim(screenName)
    if (screenName = "")
        return {ok: false, msg: ""}
    names := GetPresetScreenNames(presetName)
    for n in names {
        if (n = screenName)
            return {ok: false, msg: "A screen with this name already exists in this preset."}
    }
    ; Only the currently visible preset can have an unsaved StepRows snapshot to flush. Saving it
    ; into a different preset could overwrite a same-named screen there.
    if (presetName = CurrentPresetName)
        SaveScreenToIni(presetName, CurrentScreenName, StepRows)
    section := "Preset_" presetName
    newIdx := names.Length + 1
    IniWrite newIdx, ConfigFile, section, "ScreenCount"
    IniWrite screenName, ConfigFile, section, "Screen" newIdx "Name"
    IniWrite 0, ConfigFile, section, "Screen" newIdx "StepCount"
    if (presetName = CurrentPresetName) {
        CurrentScreenName := screenName
        RefreshScreenDdlItems(presetName, screenName)
        LoadScreenSteps(presetName, screenName)
    }
    LogMsg("Screen '" screenName "' created.")
    return {ok: true, msg: "Screen '" screenName "' created."}
}

NewScreenClick(*) {
    global CurrentPresetName
    ib := InputBox("Enter a name for the new screen:", "New Screen")
    if (ib.Result != "OK" || Trim(ib.Value) = "")
        return
    result := CreateScreen(CurrentPresetName, Trim(ib.Value))
    if !result.ok
        MsgBox result.msg
}

; Renames one explicit preset screen and its persisted jump/fallback references. Live dropdown and
; editor updates stay behind the active-preset check; prompt handling remains in RenameScreenClick().
RenameScreen(presetName, oldName, newName) {
    global CurrentPresetName, CurrentScreenName, ConfigFile, fallbackScreenDdl, StepRows
    newName := Trim(newName)
    if (newName = "" || newName = oldName)
        return {ok: false, msg: ""}
    names := GetPresetScreenNames(presetName)
    for n in names {
        if (n = newName)
            return {ok: false, msg: "A screen with this name already exists in this preset."}
    }
    if (presetName = CurrentPresetName && oldName = CurrentScreenName)
        SaveScreenToIni(presetName, oldName, StepRows)
    idx := ScreenIndexByName(presetName, oldName)
    if !idx
        return {ok: false, msg: ""}
    section := "Preset_" presetName
    IniWrite newName, ConfigFile, section, "Screen" idx "Name"
    RenameJumpTargetsEverywhere(presetName, oldName, newName)
    ; The Option Select "Fallback Screen" dropdown is preset-level, not per-step, so it isn't
    ; covered by RenameJumpTargetsEverywhere above - fix it up here too (both the live control,
    ; in case it's showing an unsaved change, and ini in case it isn't).
    if (presetName = CurrentPresetName && fallbackScreenDdl.Text = oldName)
        fallbackScreenDdl.Text := newName
    if (Cfg(section, "FallbackScreen", "(none)") = oldName)
        IniWrite newName, ConfigFile, section, "FallbackScreen"
    if (presetName = CurrentPresetName) {
        ; Only jump the editor to the renamed screen if it was the one actually open - renaming a
        ; DIFFERENT screen within the same open preset must not discard the open screen's unsaved
        ; StepRows by force-loading something else over them; just refresh the dropdown's labels.
        if (oldName = CurrentScreenName) {
            CurrentScreenName := newName
            RefreshScreenDdlItems(presetName, newName)
            LoadScreenSteps(presetName, newName)
        } else {
            RefreshScreenDdlItems(presetName, CurrentScreenName)
        }
    }
    LogMsg("Screen '" oldName "' renamed to '" newName "'.")
    return {ok: true, msg: "Screen '" oldName "' renamed to '" newName "'."}
}

RenameScreenClick(*) {
    global CurrentPresetName, CurrentScreenName
    ib := InputBox("Rename screen '" CurrentScreenName "' to:", "Rename Screen", , CurrentScreenName)
    if (ib.Result != "OK" || Trim(ib.Value) = "")
        return
    newName := Trim(ib.Value)
    if (newName = CurrentScreenName)
        return
    result := RenameScreen(CurrentPresetName, CurrentScreenName, newName)
    if !result.ok
        MsgBox result.msg
}

; Sweeps every screen's steps in this preset and updates any On True/On False value equal to
; `oldName` to `newName`, so a rename doesn't silently break existing jumps.
RenameJumpTargetsEverywhere(name, oldName, newName) {
    global ConfigFile
    section := "Preset_" name
    screenCount := Integer(Cfg(section, "ScreenCount", "0"))
    Loop screenCount {
        si := A_Index
        stepCount := Integer(Cfg(section, "Screen" si "StepCount", "0"))
        Loop stepCount {
            sj := A_Index
            if (Cfg(section, "Screen" si "Step" sj "OnTrueScreen", "(continue)") = oldName)
                IniWrite newName, ConfigFile, section, "Screen" si "Step" sj "OnTrueScreen"
            if (Cfg(section, "Screen" si "Step" sj "OnFalseScreen", "(continue)") = oldName)
                IniWrite newName, ConfigFile, section, "Screen" si "Step" sj "OnFalseScreen"
            if (Cfg(section, "Screen" si "Step" sj "FallbackScreen", "(none)") = oldName)
                IniWrite newName, ConfigFile, section, "Screen" si "Step" sj "FallbackScreen"

            outcomesKey := "Screen" si "Step" sj "Outcomes"
            outcomes := ParseOutcomes(Cfg(section, outcomesKey, ""))
            changed := false
            for o in outcomes {
                if (o.Screen = oldName) {
                    o.Screen := newName
                    changed := true
                }
            }
            if changed
                IniWrite SerializeOutcomes(outcomes), ConfigFile, section, outcomesKey
        }
    }
}

; Deletes an explicit preset screen and repairs persisted targets without prompting. The Click
; wrapper keeps the human confirmation; stateful editor-control writes only occur for the visible preset.
DeleteScreen(presetName, screenName) {
    global CurrentPresetName, CurrentScreenName, ConfigFile, fallbackScreenDdl
    names := GetPresetScreenNames(presetName)
    if (names.Length <= 1)
        return {ok: false, msg: "At least one screen must remain."}
    idx := ScreenIndexByName(presetName, screenName)
    if !idx
        return {ok: false, msg: ""}

    ; Capture every remaining screen's data (clearing jump targets that pointed at the one being
    ; removed) before touching the ini file.
    remaining := []
    for i, n in names {
        if (i = idx)
            continue
        steps := BuildScreenStepsFromIni(presetName, i)
        for st in steps {
            if (st.OnTrueScreen = screenName)
                st.OnTrueScreen := "(continue)"
            if (st.OnFalseScreen = screenName)
                st.OnFalseScreen := "(continue)"
            if (st.FallbackScreen = screenName)
                st.FallbackScreen := "(none)"
            if (st.OutcomesRaw != "") {
                outcomes := ParseOutcomes(st.OutcomesRaw)
                for o in outcomes {
                    if (o.Screen = screenName)
                        o.Screen := "(continue)"
                }
                st.OutcomesRaw := SerializeOutcomes(outcomes)
            }
        }
        remaining.Push({Name: n, Steps: steps})
    }

    ; Preserve every non-Screen* key (Options, DefaultMap, ...), then rebuild Screen* keys from
    ; `remaining` with compacted indices.
    section := "Preset_" presetName
    content := IniRead(ConfigFile, section, , "")
    keep := []
    for line in StrSplit(content, "`n", "`r") {
        if (line = "")
            continue
        eqPos := InStr(line, "=")
        if !eqPos
            continue
        key := SubStr(line, 1, eqPos - 1)
        if !InStr(key, "Screen") {
            ; The Option Select "Fallback Screen" setting is preset-level, not per-step - if it
            ; pointed at the screen being deleted, reset it to "(none)" instead of carrying a
            ; dangling reference forward.
            val := SubStr(line, eqPos + 1)
            if (key = "FallbackScreen" && val = screenName)
                val := "(none)"
            keep.Push({Key: key, Val: val})
        }
    }
    IniDelete ConfigFile, section
    for kv in keep
        IniWrite kv.Val, ConfigFile, section, kv.Key
    IniWrite remaining.Length, ConfigFile, section, "ScreenCount"
    for i, scr in remaining
        WriteScreenSteps(presetName, i, scr.Name, scr.Steps)

    if (presetName = CurrentPresetName) {
        if (fallbackScreenDdl.Text = screenName)
            fallbackScreenDdl.Text := "(none)"
        ; Only force the editor to jump to the first remaining screen if the one deleted was the
        ; one actually open - deleting a DIFFERENT screen in the same open preset must not discard
        ; the open screen's unsaved StepRows by force-loading something else over them.
        if (screenName = CurrentScreenName) {
            CurrentScreenName := remaining[1].Name
            RefreshScreenDdlItems(presetName, CurrentScreenName)
            LoadScreenSteps(presetName, CurrentScreenName)
        } else {
            RefreshScreenDdlItems(presetName, CurrentScreenName)
        }
    }
    LogMsg("Screen deleted.")
    return {ok: true, msg: "Screen deleted."}
}

DeleteScreenClick(*) {
    global CurrentPresetName, CurrentScreenName
    names := GetPresetScreenNames(CurrentPresetName)
    if (names.Length <= 1) {
        MsgBox "At least one screen must remain."
        return
    }
    res := MsgBox("Delete screen '" CurrentScreenName "'? Any On True/On False jumps (or Advanced Detection outcomes) pointing to it will fall back to '(continue)', and any Logic Fallback Screen pointing to it will fall back to '(none)'.", "Confirm", "YesNo")
    if (res != "Yes")
        return
    result := DeleteScreen(CurrentPresetName, CurrentScreenName)
    if !result.ok
        MsgBox result.msg
}

; Swaps the entire step lists (and names) stored at screen indices i1/i2 within a preset. Jump
; targets are stored by NAME, not index, so they keep pointing at the right screen automatically.
SwapScreens(name, i1, i2) {
    section := "Preset_" name
    screenNameAt1 := Cfg(section, "Screen" i1 "Name", "Screen " i1)
    screenNameAt2 := Cfg(section, "Screen" i2 "Name", "Screen " i2)
    steps1 := BuildScreenStepsFromIni(name, i1)
    steps2 := BuildScreenStepsFromIni(name, i2)
    WriteScreenSteps(name, i1, screenNameAt2, steps2)
    WriteScreenSteps(name, i2, screenNameAt1, steps1)
}

; Reorders a named screen in an explicit preset. A boundary move is a successful no-op. Refreshing
; the legacy screen dropdown is limited to that preset when it is currently visible in the editor.
MoveScreen(presetName, screenName, direction) {
    global CurrentPresetName, CurrentScreenName, StepRows
    if (presetName = CurrentPresetName && screenName = CurrentScreenName)
        SaveScreenToIni(presetName, screenName, StepRows)
    names := GetPresetScreenNames(presetName)
    idx := ScreenIndexByName(presetName, screenName)
    if !idx
        return {ok: false, msg: ""}
    if (direction = "up") {
        if (idx = 1)
            return {ok: true, msg: ""}
        SwapScreens(presetName, idx, idx - 1)
    } else if (direction = "down") {
        if (idx = names.Length)
            return {ok: true, msg: ""}
        SwapScreens(presetName, idx, idx + 1)
    } else {
        return {ok: false, msg: ""}
    }
    if (presetName = CurrentPresetName)
        RefreshScreenDdlItems(presetName, screenName)
    return {ok: true, msg: ""}
}

MoveScreenUpClick(*) {
    global CurrentPresetName, CurrentScreenName
    MoveScreen(CurrentPresetName, CurrentScreenName, "up")
}

MoveScreenDownClick(*) {
    global CurrentPresetName, CurrentScreenName
    MoveScreen(CurrentPresetName, CurrentScreenName, "down")
}

; ============================================================
; IMPORT A SCREEN (OR JUST A SINGLE STEP) FROM ANOTHER PRESET - OR THE SAME ONE, TO DUPLICATE
; ============================================================
; Repopulates the preset dropdown with every preset, INCLUDING the one currently being edited -
; picking the current preset here lets you duplicate one of its own screens/steps instead of only
; pulling from elsewhere. Defaults to the current preset selected, since duplicating within it is
; the more common case; switch to another preset to import from there instead.
RefreshImportPresetDdl() {
    global importPresetDdl, PresetNames, CurrentPresetName
    importPresetDdl.Delete()
    importPresetDdl.Add(PresetNames)
    importPresetDdl.Text := CurrentPresetName
    ImportPresetChanged()
}

; If `srcPreset` is the preset currently open in the editor, flushes whatever's shown in stepsLV
; for the currently open screen to ini first - so duplicating within the same preset picks up
; in-progress edits instead of stale saved data.
FlushIfCurrentPreset(srcPreset) {
    global CurrentPresetName, CurrentScreenName, StepRows
    if (srcPreset = CurrentPresetName)
        SaveScreenToIni(CurrentPresetName, CurrentScreenName, StepRows)
}

; Repopulates the screen dropdown with whichever preset is currently selected in importPresetDdl.
ImportPresetChanged(*) {
    global importPresetDdl, importScreenDdl
    importScreenDdl.Delete()
    src := importPresetDdl.Text
    if (src != "") {
        importScreenDdl.Add(GetPresetScreenNames(src))
        importScreenDdl.Choose(1)
    }
    ImportScreenChanged()
}

; Global holding the actual step objects currently listed in importStepDdl, parallel to its items
; (so ImportStepClick can pull the full settings back out via the selected index, not just text).
ImportStepDdlSteps := []

; Repopulates the component/step dropdown with every step of whichever screen is selected in
; importScreenDdl, labelled "#: Type (Label)" for easy identification.
ImportScreenChanged(*) {
    global importPresetDdl, importScreenDdl, importStepDdl, ImportStepDdlSteps
    importStepDdl.Delete()
    ImportStepDdlSteps := []
    src := importPresetDdl.Text
    screenName := importScreenDdl.Text
    if (src = "" || screenName = "")
        return
    FlushIfCurrentPreset(src)
    items := []
    for i, st in BuildScreenStepsFromIniByName(src, screenName) {
        desc := (st.Label != "") ? st.Type " (" st.Label ")" : st.Type
        items.Push(i ": " desc)
        ImportStepDdlSteps.Push(st)
    }
    importStepDdl.Add(items)
    if (items.Length > 0)
        importStepDdl.Choose(1)
}

; Finds a screen name in `name`'s preset that doesn't collide with an existing one, appending
; " (2)", " (3)", ... to `desired` as needed.
UniqueScreenName(name, desired) {
    existing := GetPresetScreenNames(name)
    candidate := desired
    n := 2
    Loop {
        collides := false
        for e in existing {
            if (e = candidate) {
                collides := true
                break
            }
        }
        if !collides
            return candidate
        candidate := desired " (" n ")"
        n += 1
    }
}

; Small popup asking whether an import should overwrite the currently open screen or be added as
; a brand new one. Blocks (via WinWaitClose) until the user picks one or cancels/closes it.
; Returns "overwrite", "new", or "" if cancelled.
ShowImportChoiceGui(srcPreset, srcScreen, destScreen) {
    global EditGui
    result := ""
    g := Gui("+Owner" EditGui.Hwnd, "Import Screen")
    g.SetFont("s10")
    g.AddText("x20 y15 w360", "Import '" srcScreen "' from preset '" srcPreset "' - how?")
    g.AddText("x20 y40 w360 h40", "'Overwrite' replaces the steps of the currently open screen ('" destScreen "'), keeping its name. 'Add as New' creates a separate screen instead.")
    btnOverwrite := g.AddButton("x20 y90 w170 h28", "Overwrite '" destScreen "'")
    btnNew := g.AddButton("x210 y90 w170 h28", "Add As New Screen")
    btnCancel := g.AddButton("x140 y128 w110", "Cancel")
    btnOverwrite.OnEvent("Click", (*) => (result := "overwrite", g.Destroy()))
    btnNew.OnEvent("Click", (*) => (result := "new", g.Destroy()))
    btnCancel.OnEvent("Click", (*) => (result := "", g.Destroy()))
    g.OnEvent("Close", (*) => (result := "", g.Destroy()))
    g.Show("w400 h170")
    WinWaitClose("ahk_id " g.Hwnd)
    return result
}

; Imports the screen picked in importPresetDdl/importScreenDdl into the currently open preset,
; either overwriting the screen currently shown in stepsLV (keeping its name) or adding the
; import as a separate new screen alongside it.
ImportScreenClick(*) {
    global importPresetDdl, importScreenDdl, CurrentPresetName, CurrentScreenName, ConfigFile, StepRows
    srcPreset := importPresetDdl.Text
    srcScreen := importScreenDdl.Text
    if (srcPreset = "" || srcScreen = "") {
        MsgBox "Pick a preset and one of its screens to import first."
        return
    }
    choice := ShowImportChoiceGui(srcPreset, srcScreen, CurrentScreenName)
    if (choice = "")
        return
    FlushIfCurrentPreset(srcPreset)
    steps := BuildScreenStepsFromIniByName(srcPreset, srcScreen)

    if (choice = "overwrite") {
        idx := ScreenIndexByName(CurrentPresetName, CurrentScreenName)
        if !idx
            return
        WriteScreenSteps(CurrentPresetName, idx, CurrentScreenName, steps)
        LoadScreenSteps(CurrentPresetName, CurrentScreenName)
        LogMsg("Screen '" CurrentScreenName "' overwritten with '" srcPreset "' > '" srcScreen "' (" steps.Length " step(s)).")
    } else {
        ; Flush whatever's currently shown for the open screen first, so it isn't lost.
        SaveScreenToIni(CurrentPresetName, CurrentScreenName, StepRows)
        newName := UniqueScreenName(CurrentPresetName, srcScreen)
        section := "Preset_" CurrentPresetName
        newIdx := GetPresetScreenNames(CurrentPresetName).Length + 1
        IniWrite newIdx, ConfigFile, section, "ScreenCount"
        WriteScreenSteps(CurrentPresetName, newIdx, newName, steps)
        CurrentScreenName := newName
        RefreshScreenDdlItems(CurrentPresetName, newName)
        LoadScreenSteps(CurrentPresetName, newName)
        LogMsg("Added new screen '" newName "' imported from '" srcPreset "' > '" srcScreen "' (" steps.Length " step(s)).")
    }
}

; Imports just the single component/step picked in importStepDdl (full settings included) by
; appending it to the end of the screen currently open in stepsLV - use Move Up/Down afterward to
; reposition it. Unlike "Import Screen", this never touches any other step already in the screen.
ImportStepClick(*) {
    global importPresetDdl, importScreenDdl, importStepDdl, StepRows, CurrentScreenName
    srcPreset := importPresetDdl.Text
    srcScreen := importScreenDdl.Text
    idx := importStepDdl.Value
    if (srcPreset = "" || srcScreen = "" || !idx) {
        MsgBox "Pick a preset, screen, and component to import first."
        return
    }
    ; Re-reads fresh from ini (rather than the cached dropdown list) so duplicating within the
    ; same preset always picks up whatever was most recently edited on the source screen.
    FlushIfCurrentPreset(srcPreset)
    steps := BuildScreenStepsFromIniByName(srcPreset, srcScreen)
    if (idx > steps.Length) {
        MsgBox "That component no longer exists in the selected screen - refresh the dropdowns and try again."
        return
    }
    st := steps[idx]
    StepRows.Push(st)
    RenderStepsLV()
    LogMsg("Imported step '" st.Type "' from '" srcPreset "' > '" srcScreen "' into screen '" CurrentScreenName "'.")
}

; Copies every key of one ini section to another (used by Rename, since a preset section can
; hold data for every screen plus options/default-map - safer than reconstructing key-by-key).
CopyIniSection(file, oldSection, newSection) {
    content := IniRead(file, oldSection, , "")
    if (content = "")
        return
    for line in StrSplit(content, "`n", "`r") {
        if (line = "")
            continue
        eqPos := InStr(line, "=")
        if !eqPos
            continue
        key := SubStr(line, 1, eqPos - 1)
        val := SubStr(line, eqPos + 1)
        IniWrite val, file, newSection, key
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

    presetListStr := Cfg("Presets", "List", "")
    if (presetListStr = "") {
        ; First run: create a default "Challenges" preset with 3 screens (Before Map Detection ->
        ; Ingame -> Round End -> back to Before), the same routine the old fixed 3-phase system
        ; used to build automatically, just expressed as explicit screen jumps now.
        IniWrite 3, ConfigFile, "Preset_Challenges", "ScreenCount"

        IniWrite "Before Map Detection", ConfigFile, "Preset_Challenges", "Screen1Name"
        IniWrite 4, ConfigFile, "Preset_Challenges", "Screen1StepCount"
        IniWrite "Option Select", ConfigFile, "Preset_Challenges", "Screen1Step1Type"
        IniWrite "Select Option", ConfigFile, "Preset_Challenges", "Screen1Step1Label"
        IniWrite "Button Click", ConfigFile, "Preset_Challenges", "Screen1Step2Type"
        IniWrite "Button 1", ConfigFile, "Preset_Challenges", "Screen1Step2Label"
        IniWrite "Detect Map", ConfigFile, "Preset_Challenges", "Screen1Step3Type"
        IniWrite "Detect Map", ConfigFile, "Preset_Challenges", "Screen1Step3Label"
        IniWrite "Ingame", ConfigFile, "Preset_Challenges", "Screen1Step3OnTrueScreen"
        IniWrite "Ingame", ConfigFile, "Preset_Challenges", "Screen1Step3OnFalseScreen"
        IniWrite "Button Click", ConfigFile, "Preset_Challenges", "Screen1Step4Type"
        IniWrite "Button 2", ConfigFile, "Preset_Challenges", "Screen1Step4Label"

        IniWrite "Ingame", ConfigFile, "Preset_Challenges", "Screen2Name"
        IniWrite 2, ConfigFile, "Preset_Challenges", "Screen2StepCount"
        IniWrite "Place Towers", ConfigFile, "Preset_Challenges", "Screen2Step1Type"
        IniWrite "Place Towers", ConfigFile, "Preset_Challenges", "Screen2Step1Label"
        IniWrite "Round End Detection", ConfigFile, "Preset_Challenges", "Screen2Step2Type"
        IniWrite "Victory", ConfigFile, "Preset_Challenges", "Screen2Step2Label"
        IniWrite "Round End", ConfigFile, "Preset_Challenges", "Screen2Step2OnTrueScreen"
        IniWrite "Ingame", ConfigFile, "Preset_Challenges", "Screen2Step2OnFalseScreen"

        IniWrite "Round End", ConfigFile, "Preset_Challenges", "Screen3Name"
        IniWrite 2, ConfigFile, "Preset_Challenges", "Screen3StepCount"
        IniWrite "Button Click", ConfigFile, "Preset_Challenges", "Screen3Step1Type"
        IniWrite "Button 3", ConfigFile, "Preset_Challenges", "Screen3Step1Label"
        IniWrite "Button Click", ConfigFile, "Preset_Challenges", "Screen3Step2Type"
        IniWrite "Button 4", ConfigFile, "Preset_Challenges", "Screen3Step2Label"

        IniWrite "Challenges", ConfigFile, "Presets", "List"
        IniWrite "Challenges", ConfigFile, "Presets", "Active"
        presetListStr := "Challenges"
    }

    PresetNames := StrSplit(presetListStr, ",")

    for n in PresetNames {
        psection := "Preset_" n

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

    presetListBox.Delete()
    presetListBox.Add(PresetNames)

    activeName := Cfg("Presets", "Active", PresetNames[1])
    activeIdx := 1
    found := false
    for idx, n in PresetNames {
        if (n = activeName) {
            found := true
            activeIdx := idx
        }
    }
    if !found {
        activeIdx := 1
        activeName := PresetNames[1]
    }

    presetListBox.Choose(activeIdx)
    CurrentPresetName := activeName
    ActivePresetName := activeName   ; the preset that runs on Start (view starts on it, too)
    LoadPreset(CurrentPresetName)
    UpdateActivePresetIndicator()
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

; "Set as Active" button: makes the currently-selected preset the one that runs on Start/F10,
; independent of which preset is being viewed/edited.
SetActivePresetClick() {
    global ActivePresetName, CurrentPresetName, presetListBox, ConfigFile
    sel := presetListBox.Text
    if (sel = "")
        sel := CurrentPresetName
    if (sel = "")
        return
    ActivePresetName := sel
    IniWrite ActivePresetName, ConfigFile, "Presets", "Active"
    UpdateActivePresetIndicator()
    LogMsg("Active preset set to '" ActivePresetName "' - this runs when you press Start.")
}

LoadPreset(name) {
    global OptData, defaultMapDdl, backXEdit, backYEdit, fallbackScreenDdl
    LoadPresetScreens(name)

    section := "Preset_" name
    Loop 3 {
        i := A_Index
        opt := OptData[i]
        opt.NameEdit.Value := Cfg(section, "Option" i "Name", "Option " i)
        opt.XEdit.Value := Cfg(section, "Option" i "X", "0")
        opt.YEdit.Value := Cfg(section, "Option" i "Y", "0")
        opt.AvailChk.Value := Integer(Cfg(section, "Option" i "Available", "1"))
        opt.PrioDdl.Text := Cfg(section, "Option" i "Priority", String(i))
        opt.MaxEdit.Value := Cfg(section, "Option" i "MaxUses", "0")
        opt.DetX := Cfg(section, "Option" i "DetX", "0")
        opt.DetY := Cfg(section, "Option" i "DetY", "0")
        opt.DetEndX := Cfg(section, "Option" i "DetEndX", "0")
        opt.DetEndY := Cfg(section, "Option" i "DetEndY", "0")
        opt.DetText := Cfg(section, "Option" i "DetText", "")
        opt.DetInvert := Integer(Cfg(section, "Option" i "DetInvert", "0"))
    }
    SetDdlTextSafe(defaultMapDdl, Cfg(section, "DefaultMap", "(none)"), "(none)")
    backXEdit.Value := Cfg(section, "BackX", "0")
    backYEdit.Value := Cfg(section, "BackY", "0")
    ; This preset's screen list was just (re)loaded above via LoadPresetScreens, so
    ; fallbackScreenDdl's items already match - just set the selection to what was saved.
    SetDdlTextSafe(fallbackScreenDdl, Cfg(section, "FallbackScreen", "(none)"), "(none)")
    LoadUsageFields(name)
    UpdateUsageBoxVisibility(name)
}

; Snapshots the Preset Settings and visible screen editor state as plain data for SavePresetToIni().
BuildPresetSaveData() {
    global CurrentScreenName, StepRows, OptData, defaultMapDdl, backXEdit, backYEdit, fallbackScreenDdl
    options := []
    for opt in OptData {
        options.Push({Name: opt.NameEdit.Value, X: opt.XEdit.Value, Y: opt.YEdit.Value,
            Available: opt.AvailChk.Value, Priority: opt.PrioDdl.Text, MaxUses: opt.MaxEdit.Value,
            DetX: opt.DetX, DetY: opt.DetY, DetEndX: opt.DetEndX, DetEndY: opt.DetEndY,
            DetText: opt.DetText, DetInvert: opt.DetInvert})
    }
    return {ScreenName: CurrentScreenName, Steps: StepRows, Options: options, DefaultMap: defaultMapDdl.Text,
        BackX: backXEdit.Value, BackY: backYEdit.Value, FallbackScreen: fallbackScreenDdl.Text}
}

; Saves a preset from explicit plain data: visible screen/steps, three option records, and the
; preset-level map/back/fallback fields. GUI callers obtain that snapshot through BuildPresetSaveData().
SavePresetToIni(name, data) {
    global ConfigFile
    SaveScreenToIni(name, data.ScreenName, data.Steps)

    section := "Preset_" name
    Loop 3 {
        i := A_Index
        opt := data.Options[i]
        IniWrite opt.Name, ConfigFile, section, "Option" i "Name"
        IniWrite opt.X, ConfigFile, section, "Option" i "X"
        IniWrite opt.Y, ConfigFile, section, "Option" i "Y"
        IniWrite opt.Available, ConfigFile, section, "Option" i "Available"
        IniWrite opt.Priority, ConfigFile, section, "Option" i "Priority"
        IniWrite opt.MaxUses, ConfigFile, section, "Option" i "MaxUses"
        IniWrite opt.DetX, ConfigFile, section, "Option" i "DetX"
        IniWrite opt.DetY, ConfigFile, section, "Option" i "DetY"
        IniWrite opt.DetEndX, ConfigFile, section, "Option" i "DetEndX"
        IniWrite opt.DetEndY, ConfigFile, section, "Option" i "DetEndY"
        IniWrite opt.DetText, ConfigFile, section, "Option" i "DetText"
        IniWrite opt.DetInvert, ConfigFile, section, "Option" i "DetInvert"
    }
    IniWrite data.DefaultMap, ConfigFile, section, "DefaultMap"
    IniWrite data.BackX, ConfigFile, section, "BackX"
    IniWrite data.BackY, ConfigFile, section, "BackY"
    IniWrite data.FallbackScreen, ConfigFile, section, "FallbackScreen"
    ; Refresh the Preset Settings tab's usage fields in case Max was just edited.
    LoadUsageFields(name)
}

RebuildPresetListBox() {
    global presetListBox, PresetNames
    presetListBox.Delete()
    presetListBox.Add(PresetNames)
}

PresetListChanged(*) {
    global CurrentPresetName, presetListBox
    ; Selecting a preset only changes which one is VIEWED/edited - not which one runs on Start.
    ; Use the "Set as Active" button to change what runs. (See SetActivePresetClick.)
    if (CurrentPresetName != "")
        SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
    CurrentPresetName := presetListBox.Text
    LoadPreset(CurrentPresetName)
}

; Creates a preset from its explicit name and reports validation/result data instead of presenting a
; dialog. The legacy preset controls remain updated here because they are still the active GUI view;
; NewPresetClick() owns only the interactive InputBox and error feedback.
CreatePreset(name) {
    global CurrentPresetName, presetListBox, PresetNames, ConfigFile, stepsLV, StepRows, OptData, defaultMapDdl, CurrentScreenName, screenDdl
    global backXEdit, backYEdit, fallbackScreenDdl
    name := Trim(name)
    if (name = "")
        return {ok: false, msg: ""}
    for n in PresetNames {
        if (n = name)
            return {ok: false, msg: "A preset with this name already exists."}
    }
    ; Only the currently-viewed preset can have unsaved in-editor edits to flush - same guard
    ; RenamePreset/DeletePreset already use.
    if (CurrentPresetName != "")
        SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
    PresetNames.Push(name)
    presetListBox.Add([name])
    presetListBox.Choose(PresetNames.Length)
    CurrentPresetName := name

    ; Build the new preset's default data directly, rather than writing these defaults into the
    ; native GUI's option-editor controls and reading them back out via BuildPresetSaveData() - the
    ; engine/IPC-reachable data-mutation logic must not depend on GUI controls that a later phase
    ; deletes. The GUI-control writes right below are no longer the SOURCE of the persisted data
    ; (SavePresetToIni() below is called with defaultOptions directly) - they only keep this
    ; still-live editor's own display consistent with it. LoadUsageFields(), a side effect of
    ; SavePresetToIni() further below, does read OptData[i].NameEdit.Value back, but only after this
    ; loop has already set it to the exact same default just written to defaultOptions.
    defaultOptions := []
    Loop 3 {
        i := A_Index
        defaultOptions.Push({Name: "Option " i, X: 0, Y: 0, Available: 1, Priority: i, MaxUses: 0,
            DetX: 0, DetY: 0, DetEndX: 0, DetEndY: 0, DetText: "", DetInvert: 0})
        opt := OptData[i]
        opt.NameEdit.Value := "Option " i
        opt.XEdit.Value := "0"
        opt.YEdit.Value := "0"
        opt.AvailChk.Value := 1
        opt.PrioDdl.Text := String(i)
        opt.MaxEdit.Value := "0"
        opt.DetX := "0"
        opt.DetY := "0"
        opt.DetEndX := "0"
        opt.DetEndY := "0"
        opt.DetText := ""
        opt.DetInvert := 0
    }
    defaultMapDdl.Text := "(none)"
    backXEdit.Value := "0"
    backYEdit.Value := "0"
    fallbackScreenDdl.Text := "(none)"
    IniWrite 1, ConfigFile, "Preset_" name, "ScreenCount"
    IniWrite "Screen 1", ConfigFile, "Preset_" name, "Screen1Name"
    IniWrite 0, ConfigFile, "Preset_" name, "Screen1StepCount"
    CurrentScreenName := "Screen 1"
    screenDdl.Delete()
    screenDdl.Add(["Screen 1"])
    screenDdl.Text := "Screen 1"
    StepRows := []
    RenderStepsLV()
    RefreshJumpTargetDdls(name)
    SavePresetToIni(name, {ScreenName: "Screen 1", Steps: [], Options: defaultOptions,
        DefaultMap: "(none)", BackX: 0, BackY: 0, FallbackScreen: "(none)"})
    IniWrite JoinList(PresetNames), ConfigFile, "Presets", "List"
    ; A new preset is selected for editing but does NOT auto-become the one that runs on Start -
    ; use "Set as Active" for that. (Leaves ActivePresetName untouched.)
    try editingLabel.Text := "Editing: " CurrentPresetName
    LogMsg("Preset '" name "' created.")
    return {ok: true, msg: "Preset '" name "' created."}
}

NewPresetClick(*) {
    ib := InputBox("Enter a name for the new preset:", "New Preset")
    if (ib.Result != "OK" || Trim(ib.Value) = "")
        return
    result := CreatePreset(Trim(ib.Value))
    if !result.ok
        MsgBox result.msg
}

; Exports the currently selected preset (its whole [Preset_<name>] section - screens, steps,
; options, back button, default map) to a standalone .ini file under a neutral [Preset] header, so
; it can be backed up or shared. Coordinates are window-relative percentages, so the preset stays
; usable on another screen/resolution. Map profiles are NOT bundled (they're shared across presets).
ExportPresetClick(*) {
    global CurrentPresetName, ConfigFile
    if (CurrentPresetName = "") {
        MsgBox "No preset selected to export."
        return
    }
    SavePresetToIni(CurrentPresetName, BuildPresetSaveData())   ; flush any in-editor changes so the export is current
    file := FileSelect("S16", CurrentPresetName ".ini", "Export Preset", "Preset files (*.ini)")
    if (file = "")
        return
    if !RegExMatch(file, "\.ini$")
        file .= ".ini"
    try FileDelete file
    content := IniRead(ConfigFile, "Preset_" CurrentPresetName, , "")
    IniWrite CurrentPresetName, file, "PresetExport", "SourceName"
    for line in StrSplit(content, "`n", "`r") {
        eq := InStr(line, "=")
        if eq
            IniWrite SubStr(line, eq + 1), file, "Preset", SubStr(line, 1, eq - 1)
    }
    LogMsg("Preset '" CurrentPresetName "' exported.")
    MsgBox "Exported preset '" CurrentPresetName "' to:`n" file
}

; Imports a preset from an .ini file created by Export, as a NEW preset (prompts for a name,
; refusing to overwrite an existing one). Fixes up nothing else - referenced map profiles must
; already exist locally (otherwise the preset's Default Map falls back to '(none)').
ImportPresetFileClick(*) {
    global ConfigFile, PresetNames, presetListBox, CurrentPresetName
    file := FileSelect(3, , "Import Preset", "Preset files (*.ini)")
    if (file = "")
        return
    content := IniRead(file, "Preset", , "")
    if (content = "") {
        MsgBox "That file doesn't look like an exported preset (no [Preset] section found)."
        return
    }
    defaultName := RegExReplace(RegExReplace(file, ".*[\\/]", ""), "\.ini$", "")
    ib := InputBox("Name for the imported preset:", "Import Preset", "w320 h130", defaultName)
    if (ib.Result != "OK" || Trim(ib.Value) = "")
        return
    name := Trim(ib.Value)
    for n in PresetNames {
        if (n = name) {
            MsgBox "A preset with this name already exists - pick a different name."
            return
        }
    }
    if (CurrentPresetName != "")
        SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
    section := "Preset_" name
    for line in StrSplit(content, "`n", "`r") {
        eq := InStr(line, "=")
        if eq
            IniWrite SubStr(line, eq + 1), ConfigFile, section, SubStr(line, 1, eq - 1)
    }
    PresetNames.Push(name)
    presetListBox.Add([name])
    presetListBox.Choose(PresetNames.Length)
    CurrentPresetName := name
    LoadPreset(name)
    IniWrite JoinList(PresetNames), ConfigFile, "Presets", "List"
    ; Imported preset is opened for editing but does not auto-become the active (running) preset.
    try editingLabel.Text := "Editing: " CurrentPresetName
    LogMsg("Preset '" name "' imported.")
    MsgBox "Imported as preset '" name "'."
}

; Renames a preset from explicit names, preserving the old-section flush/copy order and all legacy
; view updates. RenamePresetClick() is intentionally just the prompt and local error-feedback layer.
RenamePreset(oldName, newName) {
    global CurrentPresetName, presetListBox, PresetNames, ConfigFile, ActivePresetName, Running, RunningPresetName
    newName := Trim(newName)
    if (newName = "" || newName = oldName)
        return {ok: false, msg: ""}
    ; RunSteps() resolves the running preset's ini section from RunningPresetName on every read - a
    ; rename would move that section out from under it mid-run, silently falling back to every
    ; field's default instead of erroring or using stale-but-correct values.
    if (Running && oldName = RunningPresetName)
        return {ok: false, msg: "Cannot rename the preset that is currently running - stop the macro first."}
    for n in PresetNames {
        if (n = newName)
            return {ok: false, msg: "A preset with this name already exists."}
    }
    ; Only the currently-viewed preset can have unsaved in-editor edits to flush - renaming a
    ; different, not-currently-viewed preset skips the flush and just copies its already-
    ; persisted section as-is (CopyIniSection always runs; that's what actually moves the data).
    if (oldName = CurrentPresetName)
        SavePresetToIni(oldName, BuildPresetSaveData())
    CopyIniSection(ConfigFile, "Preset_" oldName, "Preset_" newName)
    IniDelete ConfigFile, "Preset_" oldName
    newIdx := 1
    for idx, n in PresetNames {
        if (n = oldName) {
            PresetNames[idx] := newName
            newIdx := idx
            break
        }
    }
    ; If the renamed preset was the active (running) one, keep the active pointer valid.
    if (ActivePresetName = oldName) {
        ActivePresetName := newName
        IniWrite ActivePresetName, ConfigFile, "Presets", "Active"
    }
    RebuildPresetListBox()
    ; Only force the legacy editor to switch away if it was showing the preset just renamed.
    if (oldName = CurrentPresetName) {
        presetListBox.Choose(newIdx)
        CurrentPresetName := newName
        try editingLabel.Text := "Editing: " CurrentPresetName
    } else {
        try presetListBox.Choose(PresetIndex(CurrentPresetName))
    }
    IniWrite JoinList(PresetNames), ConfigFile, "Presets", "List"
    UpdateActivePresetIndicator()
    LogMsg("Preset renamed to '" newName "'.")
    return {ok: true, msg: "Preset renamed to '" newName "'."}
}

RenamePresetClick(*) {
    global CurrentPresetName
    ib := InputBox("Rename preset '" CurrentPresetName "' to:", "Rename Preset", , CurrentPresetName)
    if (ib.Result != "OK" || Trim(ib.Value) = "")
        return
    newName := Trim(ib.Value)
    if (newName = CurrentPresetName)
        return
    result := RenamePreset(CurrentPresetName, newName)
    if !result.ok
        MsgBox result.msg
}

; Deletes the named preset without interacting with the user. The wrapper owns the existing
; last-preset message and destructive confirmation; direct callers receive the same guard result.
DeletePreset(name) {
    global CurrentPresetName, presetListBox, PresetNames, ConfigFile, stepsLV, ActivePresetName, Running, RunningPresetName
    if (PresetNames.Length <= 1)
        return {ok: false, msg: "At least one preset must remain."}
    ; Same reasoning as RenamePreset(): deleting the running preset's ini section out from under
    ; RunSteps() mid-run would silently fall back to every field's default.
    if (Running && name = RunningPresetName)
        return {ok: false, msg: "Cannot delete the preset that is currently running - stop the macro first."}
    deletedName := name
    IniDelete ConfigFile, "Preset_" name
    newList := []
    for n in PresetNames {
        if (n != name)
            newList.Push(n)
    }
    PresetNames := newList
    RebuildPresetListBox()
    ; Only force the legacy editor to switch away if the preset it was showing is the one that
    ; just got deleted - deleting a different, not-currently-viewed preset must not disturb it.
    if (name = CurrentPresetName) {
        CurrentPresetName := PresetNames[1]
        presetListBox.Choose(1)
        LoadPreset(CurrentPresetName)
        try editingLabel.Text := "Editing: " CurrentPresetName
    } else {
        try presetListBox.Choose(PresetIndex(CurrentPresetName))
    }
    IniWrite JoinList(PresetNames), ConfigFile, "Presets", "List"
    ; If the deleted preset was the active (running) one, fall the active pointer back to the first.
    if (ActivePresetName = deletedName || ActivePresetName = "") {
        ActivePresetName := PresetNames[1]
        IniWrite ActivePresetName, ConfigFile, "Presets", "Active"
    }
    UpdateActivePresetIndicator()
    LogMsg("Preset deleted.")
    return {ok: true, msg: "Preset deleted."}
}

DeletePresetClick(*) {
    global CurrentPresetName, PresetNames
    if (PresetNames.Length <= 1) {
        MsgBox "At least one preset must remain."
        return
    }
    res := MsgBox("Delete preset '" CurrentPresetName "'?", "Confirm", "YesNo")
    if (res != "Yes")
        return
    result := DeletePreset(CurrentPresetName)
    if !result.ok
        MsgBox result.msg
}

; ============================================================
; STEP EDITOR
; ============================================================
; The step list (stepsLV) is a rendered VIEW of the StepRows array (the real store, which round-
; trips to ini). RenderStepsLV rebuilds every row from StepRows via StepDisplayCells, which shows
; only the columns each step type actually uses - a Wait step has no X/Y, a detection step's OCR
; region isn't shown as raw X/Y numbers, etc. - keeping the table readable while every field still
; lives in StepRows.

; Which of the 17 columns each step type shows. Everything not listed is blank for that type, so
; irrelevant coordinates (and a Logic step's OCR region) never clutter the table.
StepDisplayCells(s, num) {
    t := s.Type
    isLogic := IsLogicStepType(t)
    isDrag := (t = "Drag")
    isZoom := (t = "Zoom Out")
    isCustom := (t = "Custom Detection")
    usesPoint := (t = "Button Click" || t = "Press Start Button" || t = "Restart Stage Button" || isDrag)

    c4 := isZoom ? s.X : (usesPoint ? s.X : "")               ; X / Duration / Ticks
    c5 := usesPoint ? s.Y : ""                                ; Y (Zoom Out has no Y; Logic region hidden)
    c6 := isDrag ? s.EndX : ""                                ; End X (Drag only)
    c7 := isDrag ? s.EndY : ""                                ; End Y (Drag only)
    c8 := isDrag ? s.DragMs : ""                              ; Drag (ms) (Drag only)
    c9 := s.OncePerCycle ? "Yes" : ""                         ; Once/Cycle (blank when off, to declutter)
    onTrue := s.OnTrueScreen
    c10 := (onTrue = "" || onTrue = "(continue)") ? "" : onTrue                     ; On True / unconditional jump
    onFalse := s.OnFalseScreen
    c11 := (isLogic && onFalse != "" && onFalse != "(continue)") ? onFalse : ""     ; On False (Logic only)
    c12 := (s.Seconds != "" && s.Seconds != "0") ? s.Seconds : ""                   ; Wait After (s)
    fbOn := (isLogic && s.FallbackEnabled)
    c13 := fbOn ? "Yes" : ""                                  ; FB After N
    c14 := fbOn ? s.FallbackMaxAttempts : ""                  ; FB Max
    c15 := (fbOn && s.FallbackScreen != "" && s.FallbackScreen != "(none)") ? s.FallbackScreen : ""  ; FB Screen
    advOn := (isCustom && s.Advanced)
    c16 := advOn ? "Yes" : ""                                 ; Advanced
    c17 := advOn ? s.OutcomesRaw : ""                         ; Outcomes
    return [num, t, s.Label, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15, c16, c17]
}

; Rebuilds the whole step-list view from StepRows.
RenderStepsLV() {
    global stepsLV, StepRows
    stepsLV.Delete()
    for i, s in StepRows
        stepsLV.Add("", StepDisplayCells(s, i)*)
}

; Builds a step object (ini schema) from the current step-editor field values.
StepFromEditor() {
    global stepTypeDdl, stepLabelEdit, stepXEdit, stepYEdit, stepSecEdit
    global dragEndXEdit, dragEndYEdit, dragMsEdit, oncePerCycleChk, stepOnTrueDdl, stepOnFalseDdl
    global stepFallbackChk, stepFallbackMaxEdit, stepFallbackScreenDdl, stepAdvancedChk, EditingOutcomes
    isLogic := IsLogicStepType(stepTypeDdl.Text)
    advEnabled := (stepTypeDdl.Text = "Custom Detection") && stepAdvancedChk.Value
    return {Type: stepTypeDdl.Text, Label: stepLabelEdit.Value,
        X: stepXEdit.Value, Y: stepYEdit.Value, EndX: dragEndXEdit.Value, EndY: dragEndYEdit.Value,
        DragMs: dragMsEdit.Value, OncePerCycle: (oncePerCycleChk.Value ? 1 : 0), AlreadyDone: false,
        Seconds: stepSecEdit.Value, OnTrueScreen: stepOnTrueDdl.Text,
        OnFalseScreen: (isLogic ? stepOnFalseDdl.Text : "(continue)"),
        FallbackEnabled: ((isLogic && stepFallbackChk.Value) ? 1 : 0),
        FallbackMaxAttempts: stepFallbackMaxEdit.Value, FallbackScreen: stepFallbackScreenDdl.Text,
        FallbackAttemptCount: 0, Advanced: (advEnabled ? 1 : 0),
        OutcomesRaw: (advEnabled ? SerializeOutcomes(EditingOutcomes) : "")}
}

; Loads a step object into the editor fields.
LoadEditorFromStep(s) {
    global stepTypeDdl, stepLabelEdit, stepXEdit, stepYEdit, stepSecEdit
    global dragEndXEdit, dragEndYEdit, dragMsEdit, oncePerCycleChk, stepOnTrueDdl, stepOnFalseDdl
    global stepFallbackChk, stepFallbackMaxEdit, stepFallbackScreenDdl, stepAdvancedChk, EditingOutcomes
    SetDdlTextSafe(stepTypeDdl, s.Type, "Button Click")
    stepLabelEdit.Value := s.Label
    stepXEdit.Value := s.X
    stepYEdit.Value := s.Y
    dragEndXEdit.Value := s.EndX
    dragEndYEdit.Value := s.EndY
    dragMsEdit.Value := s.DragMs
    oncePerCycleChk.Value := s.OncePerCycle ? 1 : 0
    SetDdlTextSafe(stepOnTrueDdl, s.OnTrueScreen, "(continue)")
    SetDdlTextSafe(stepOnFalseDdl, s.OnFalseScreen, "(continue)")
    stepSecEdit.Value := s.Seconds
    stepFallbackChk.Value := s.FallbackEnabled ? 1 : 0
    stepFallbackMaxEdit.Value := s.FallbackMaxAttempts
    SetDdlTextSafe(stepFallbackScreenDdl, s.FallbackScreen, "(none)")
    stepAdvancedChk.Value := s.Advanced ? 1 : 0
    EditingOutcomes := ParseOutcomes(s.OutcomesRaw)
    UpdateStepEditorLabels()
}

LoadEditorFromSelection(*) {
    global stepsLV, StepRows
    row := stepsLV.GetNext(0, "Focused")
    if (!row || row > StepRows.Length)
        return
    LoadEditorFromStep(StepRows[row])
}

; Clears every step-editor field back to its default (EXCEPT the type dropdown) and deselects any
; selected list row - shared by ResetStepEditor and StepTypeChangedByUser. Does NOT refresh the
; type-dependent field visibility itself; callers do that via UpdateStepEditorLabels afterwards.
ClearStepEditorFields() {
    global stepsLV, stepLabelEdit, stepXEdit, stepYEdit, stepSecEdit
    global dragEndXEdit, dragEndYEdit, dragMsEdit, oncePerCycleChk, stepOnTrueDdl, stepOnFalseDdl
    global stepFallbackChk, stepFallbackMaxEdit, stepFallbackScreenDdl, stepAdvancedChk, EditingOutcomes
    stepLabelEdit.Value := ""
    stepXEdit.Value := "0"
    stepYEdit.Value := "0"
    dragEndXEdit.Value := "0"
    dragEndYEdit.Value := "0"
    dragMsEdit.Value := "500"
    stepSecEdit.Value := "0"
    oncePerCycleChk.Value := 0
    SetDdlTextSafe(stepOnTrueDdl, "(continue)", "(continue)")
    SetDdlTextSafe(stepOnFalseDdl, "(continue)", "(continue)")
    stepFallbackChk.Value := 0
    stepFallbackMaxEdit.Value := "5"
    SetDdlTextSafe(stepFallbackScreenDdl, "(none)", "(none)")
    stepAdvancedChk.Value := 0
    EditingOutcomes := []
    row := stepsLV.GetNext(0, "Focused")
    if row
        try stepsLV.Modify(row, "-Select -Focus")
}

; Resets the step editor back to a fresh, default "Button Click" step. Called after each "Add Step"
; so the next one starts blank.
ResetStepEditor(*) {
    global stepTypeDdl
    stepTypeDdl.Text := "Button Click"
    ClearStepEditorFields()
    UpdateStepEditorLabels()
}

AddStepClick(*) {
    global StepRows
    StepRows.Push(StepFromEditor())
    RenderStepsLV()
    ResetStepEditor()
}

UpdateSelectedClick(*) {
    global stepsLV, StepRows
    row := stepsLV.GetNext(0, "Focused")
    if (!row || row > StepRows.Length) {
        LogMsg("No step selected.")
        return
    }
    StepRows[row] := StepFromEditor()
    RenderStepsLV()
    stepsLV.Modify(row, "Select Focus")
}

RemoveSelectedClick(*) {
    global stepsLV, StepRows
    row := stepsLV.GetNext(0, "Focused")
    if (!row || row > StepRows.Length)
        return
    StepRows.RemoveAt(row)
    RenderStepsLV()
}

MoveUpClick(*) {
    global stepsLV, StepRows
    row := stepsLV.GetNext(0, "Focused")
    if (!row || row = 1)
        return
    tmp := StepRows[row], StepRows[row] := StepRows[row - 1], StepRows[row - 1] := tmp
    RenderStepsLV()
    stepsLV.Modify(row - 1, "Focus Select")
}

MoveDownClick(*) {
    global stepsLV, StepRows
    row := stepsLV.GetNext(0, "Focused")
    if (!row || row = StepRows.Length)
        return
    tmp := StepRows[row], StepRows[row] := StepRows[row + 1], StepRows[row + 1] := tmp
    RenderStepsLV()
    stepsLV.Modify(row + 1, "Focus Select")
}

; Moves the step at `from` to position `to` (used by drag-to-reorder).
StepMoveRow(from, to) {
    global stepsLV, StepRows
    if (from = to || from < 1 || to < 1 || from > StepRows.Length || to > StepRows.Length)
        return
    item := StepRows.RemoveAt(from)
    StepRows.InsertAt(to, item)
    RenderStepsLV()
    stepsLV.Modify(to, "Select Focus")
}

; --- Drag-to-reorder: the ListView fires LVN_BEGINDRAG (-9) when the user starts dragging a row
; with the left button. We track the mouse with a timer and drop when the button is released,
; reordering StepRows to match. ---
StepsLVBeginDrag(ctrl, lParam) {
    global stepsLV, StepDragFrom, StepDragging
    row := stepsLV.GetNext(0, "Focused")
    if (!row)
        return
    StepDragFrom := row
    StepDragging := true
    ToolTip "Drag to reorder - release to drop."
    SetTimer StepsLVDragTick, 25
}

StepsLVDragTick() {
    global stepsLV, StepDragFrom, StepDragging, StepRows
    if (!StepDragging)
        return
    if GetKeyState("LButton", "P") {
        target := LVRowUnderMouse(stepsLV)
        if (target && target != StepDragFrom)
            ToolTip "Drop here -> position " target " of " StepRows.Length "."
        return
    }
    ; Button released - finalize the drop.
    SetTimer StepsLVDragTick, 0
    StepDragging := false
    ToolTip()
    target := LVRowUnderMouse(stepsLV)
    if (target && target != StepDragFrom)
        StepMoveRow(StepDragFrom, target)
    StepDragFrom := 0
}

; Returns the 1-based step-list row under the mouse cursor (0 if none / past the last row).
LVRowUnderMouse(lv) {
    hwnd := lv.Hwnd
    pt := Buffer(8, 0)
    DllCall("GetCursorPos", "Ptr", pt)
    DllCall("ScreenToClient", "Ptr", hwnd, "Ptr", pt)
    hti := Buffer(24, 0)
    NumPut("Int", NumGet(pt, 0, "Int"), hti, 0)
    NumPut("Int", NumGet(pt, 4, "Int"), hti, 4)
    row := DllCall("SendMessage", "Ptr", hwnd, "UInt", 0x1012, "Ptr", 0, "Ptr", hti, "Ptr")  ; LVM_HITTEST
    return (row >= 0) ? row + 1 : 0
}

SavePresetClick(*) {
    global CurrentPresetName
    SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
    LogMsg("Preset '" CurrentPresetName "' saved.")
}

; Starts the macro beginning at the currently selected step on the currently open screen -
; skipping everything before it on this screen (later screens, reached via jumps/fallthrough,
; still run normally from their own start). Flushes the visible preset to ini first, so the
; running macro sees exactly what's shown here right now, unsaved edits included.
StartFromStepClick(*) {
    global stepsLV, CurrentPresetName, CurrentScreenName
    row := stepsLV.GetNext(0, "Focused")
    if !row {
        MsgBox "Select a step first."
        return
    }
    SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
    ; Run the preset currently open here (not the "active" one) - starting at the selected step.
    StartMacroWithLocalFeedback(CurrentScreenName, row, false)
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
    global DisconnectRestartPending, DisconnectLastCheckTick, DryRun, dryRunChk
    global ActivePresetName, presetListBox, editingLabel
    global PendingPresetSwitch, PresetSwitchRestartPending, ConfigFile, StopRequested, MacroActive
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
    ; Fresh run: drop any queued switch / stale stop from a previous session. PendingPresetSwitch and
    ; PresetSwitchRestartPending can't actually be set this early (QUEUE_PRESET needs Running; the commit
    ; flag is only set at a cycle boundary), but clearing them keeps a clean slate.
    PendingPresetSwitch := ""
    PresetSwitchRestartPending := false
    StopRequested := false
    Critical "Off"
    ; MacroActive now stays true for the whole session, INCLUDING restart prep (where Running is briefly
    ; false). The try/finally below guarantees it is cleared on EVERY exit - an early error return, a normal
    ; stop, a StopRequested abort, or an unexpected error mid-run - otherwise a stuck-true flag would (via
    ; the guard above) permanently block Start.
    try {
        ; Normal Start/F10 runs the ACTIVE preset (chosen via "Set as Active"), which may differ from the
        ; one currently being viewed. Switch the whole view over to it first, so the run reads the right
        ; preset's options/steps. "Start Macro From This Step" (useActive=false) runs the viewed preset.
        ; RESTORED to its original, pre-migration form deliberately: RunSteps() no longer NEEDS any of
        ; this refreshed (it reads Cfg(presetSection, ...) via RunningPresetName directly now), but the
        ; still-live native GUI does - two review passes caught real invariant breaks from trying to
        ; drop pieces of this as "just display sync": (1) unsaved edits in whatever preset the editor is
        ; currently showing would be silently discarded rather than flushed, (2) LoadPreset() must run
        ; to keep "CurrentPresetName = RunningPresetName means the open editor's state belongs to this
        ; preset" true, since SyncEditGuiToRunningStep()/the editor's close-Save path both trust that
        ; invariant and would otherwise save stale data over the new preset's real data, (3)
        ; presetListBox's selection is read back by SetActivePresetClick(), not just displayed. Leave
        ; this block exactly as-is until the native GUI itself is deleted in a later phase.
        if (useActive && ActivePresetName != "" && ActivePresetName != CurrentPresetName && PresetIndex(ActivePresetName)) {
            SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
            CurrentPresetName := ActivePresetName
            try presetListBox.Choose(PresetIndex(ActivePresetName))
            LoadPreset(CurrentPresetName)
            try editingLabel.Text := "Editing: " CurrentPresetName
        }
        ; Latch Dry Run for the whole run from the checkbox (so toggling it mid-run has no effect).
        DryRun := dryRunChk.Value ? true : false
        ClearLog()
        if DryRun
            LogMsg("DRY RUN - actions are logged but NOT performed (no clicks/keys/drags).")

        ; Warm up the OCR helper now so the first detection step doesn't pay its one-time startup
        ; mid-run. Non-fatal if it can't start - detection falls back to the one-shot path.
        EnsureOcrServer()

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
                    ; RESTORED to its original, pre-migration form - see the "useActive" switch's comment
                    ; above for why: RunSteps() no longer needs any of this refreshed, but the still-live
                    ; native GUI does (unsaved-edit flush, the CurrentPresetName/editor-state invariant,
                    ; and presetListBox's selection being read back elsewhere).
                    SavePresetToIni(CurrentPresetName, BuildPresetSaveData())
                    CurrentPresetName := newName
                    ActivePresetName := newName
                    try presetListBox.Choose(PresetIndex(newName))
                    LoadPreset(CurrentPresetName)
                    try editingLabel.Text := "Editing: " CurrentPresetName
                    try IniWrite ActivePresetName, ConfigFile, "Presets", "Active"
                    UpdateActivePresetIndicator()
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

    trueStartIdx := FindStartScreenIndex(PresetScreens)
    screenIdx := startScreenIdx ? startScreenIdx : trueStartIdx
    cycleCount := 0
    ScreenRepeatCount := 0
    StepRepeatCount := 0
    ScreenRunCounts := Map()
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
        RunningScreenName := scr.Name
        ScreenRunCounts[scr.Name] := (ScreenRunCounts.Has(scr.Name) ? ScreenRunCounts[scr.Name] : 0) + 1
        RenderScreenCountPanel()
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

            extraWait := SafeNum(Cfg("General", "RoundWaitSeconds", "0"))
            if (extraWait > 0) {
                WaitSecondsInterruptible(extraWait, "Waiting before next cycle: ")
                LogMsg("Cycle wait complete.")
            }

            ; NOTE: the full config is deliberately NOT re-saved every cycle - it doesn't change
            ; during a run, and per-option "used today" counters already persist themselves the
            ; moment they change (see IncrementOptionUsed). Re-writing the entire config (every
            ; screen, step and map profile) each cycle was pure disk churn and caused lag on
            ; fast-cycling presets. Config is saved at macro start, on manual Save, and on exit.

            maxR := SafeInt(Cfg("General", "MaxRounds", "0"))
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
SyncEditGuiToRunningStep(screenName, stepIdx) {
    global EditGuiVisible, RunningPresetName, CurrentPresetName, CurrentScreenName, screenDdl, stepsLV, StepRows
    if (screenName = "" || !EditGuiVisible || RunningPresetName != CurrentPresetName)
        return
    if (CurrentScreenName != screenName) {
        SaveScreenToIni(CurrentPresetName, CurrentScreenName, StepRows)
        CurrentScreenName := screenName
        screenDdl.Text := screenName
        LoadScreenSteps(CurrentPresetName, screenName)
    }
    try stepsLV.Modify(stepIdx, "Select Focus Vis")
}

; Resolves which map to act on: the map detected via "Detect Map" this cycle, or the preset's
; configured Default Map if none was detected (or detection hasn't run yet). Uses the ACTUALLY
; RUNNING preset (RunningPresetName), not whatever's selected in the GUI (CurrentPresetName) - the
; Default Map is per-preset, so selecting a different preset in the list mid-run must not change
; which map the running preset falls back to.
ResolveMapName() {
    global LastDetectedMap, RunningPresetName
    mapName := LastDetectedMap
    if (mapName = "") {
        defaultMap := Cfg("Preset_" RunningPresetName, "DefaultMap", "(none)")
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
; Uses the map's own custom camera/zoom steps if it has them enabled, otherwise the shared
; [General] ones. With force=true the shared once-per-cycle guard is bypassed (the actions run
; every time this is called), but the flag is still set afterwards - used by the explicit "Camera
; Setup" step, whose own repetition is governed solely by that step's "Once per cycle" checkbox.
RunMapAdvStepsForMap(mapName, clickDelay, force := false) {
    global Running, MapAdvStepsDoneThisCycle
    if (MapAdvStepsDoneThisCycle && !force)
        return   ; already ran the camera/zoom actions for this cycle
    mapSection := "MapProfile_" mapName
    useCustom := SafeInt(Cfg(mapSection, "CustomCamera", "0"))
    camSection := useCustom ? mapSection : "General"
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
    clickDelay := SafeInt(Cfg("General", "ClickDelayMs", "300"))
    placeTowerDelay := SafeInt(Cfg("General", "PlaceTowerDelayMs", "100"))
    presetSection := "Preset_" RunningPresetName

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

        SyncEditGuiToRunningStep(RunningScreenName, stepIdx)
        RunningStepDescription := step.Type . (step.Label != "" ? " (" step.Label ")" : "")
        RenderStatsPanel()

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
                        if SafeInt(Cfg("General", "AfterPlaceClick", "0")) {
                            ap := AbsXY(Cfg("General", "AfterPlaceClickX", "0"), Cfg("General", "AfterPlaceClickY", "0"))
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

