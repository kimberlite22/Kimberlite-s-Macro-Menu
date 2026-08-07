[CmdletBinding()]
param(
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

function Invoke-Download {
    param(
        [Parameter(Mandatory)] [string]$Uri,
        [Parameter(Mandatory)] [string]$Destination
    )

    $curl = Get-Command 'curl.exe' -ErrorAction SilentlyContinue
    if ($curl) {
        $arguments = @('--fail', '--location', '--retry', '3', '--retry-delay', '2')
        $arguments += @('--output', $Destination, $Uri)
        & $curl.Source @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Download failed with exit code ${LASTEXITCODE}: $Uri"
        }
        return
    }

    Invoke-WebRequest -Uri $Uri -OutFile $Destination
}

function Get-GitHubZipAsset {
    param(
        [Parameter(Mandatory)] [string]$Repository,
        [Parameter(Mandatory)] [scriptblock]$Filter
    )

    $headers = @{
        Accept = 'application/vnd.github+json'
        'User-Agent' = 'Kimberlites-Macro-Menu local build'
    }
    $release = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/$Repository/releases/latest"
    $asset = @($release.assets | Where-Object -FilterScript $Filter)[0]
    if (-not $asset) {
        throw "No matching ZIP asset was found in the latest $Repository release."
    }
    return $asset
}

function Stop-ProcessTree {
    param(
        [Parameter(Mandatory)] [int]$ProcessId
    )

    # PyInstaller onefile uses a bootloader process and a child process running the same image.
    try {
        & taskkill.exe /F /T /PID $ProcessId 2>$null | Out-Null
    } catch {
    }

    $deadline = (Get-Date).AddSeconds(5)
    do {
        $process = $null
        try {
            $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        } catch {
        }
        if (-not $process) {
            return
        }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $deadline)
}

function Stop-ProcessesUsingFile {
    param(
        [Parameter(Mandatory)] [string]$Path
    )

    $resolvedPath = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $resolvedPath) {
        return
    }
    $fullPath = $resolvedPath.Path

    try {
        $processes = Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object { $_.Path -and $_.Path.Equals($fullPath, [System.StringComparison]::OrdinalIgnoreCase) }
    } catch {
        return
    }

    foreach ($process in $processes) {
        Write-Host "Stopping stale process $($process.Name) (PID $($process.ProcessId)) using $fullPath."
        Stop-ProcessTree -ProcessId ([int]$process.ProcessId)
    }
}

function Ensure-PortableGo {
    $goRoot = Join-Path $repoRoot '.build\go'
    $goExe = Join-Path $goRoot 'bin\go.exe'
    if (Test-Path -LiteralPath $goExe) {
        return $goExe
    }

    $goMod = Get-Content -LiteralPath 'remote\agent\go.mod' -Raw
    $match = [regex]::Match($goMod, '(?m)^go\s+(\d+\.\d+(?:\.\d+)?)\s*$')
    if (-not $match.Success) {
        throw 'Could not determine the required Go version from remote/agent/go.mod.'
    }
    $goVersion = $match.Groups[1].Value
    if (($goVersion -split '\.').Count -eq 2) {
        $goVersion += '.0'
    }

    New-Item -ItemType Directory -Path '.build' -Force | Out-Null
    $zipPath = Join-Path $repoRoot '.build\go.zip'
    Write-Host "Downloading Go $goVersion..."
    Invoke-Download -Uri "https://go.dev/dl/go$goVersion.windows-amd64.zip" -Destination $zipPath
    Expand-Archive -LiteralPath $zipPath -DestinationPath '.build' -Force
    if (-not (Test-Path -LiteralPath $goExe)) {
        throw 'The downloaded Go archive did not contain bin/go.exe.'
    }
    return $goExe
}

function Ensure-AutoHotkeyTools {
    $compiler = Get-ChildItem -LiteralPath '.build\compiler' -Recurse -Filter 'Ahk2Exe.exe' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $base = Get-ChildItem -LiteralPath '.build\ahk' -Recurse -Filter 'AutoHotkey64.exe' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($compiler -and $base) {
        return @{ Compiler = $compiler.FullName; Base = $base.FullName }
    }

    New-Item -ItemType Directory -Path '.build\ahk', '.build\compiler' -Force | Out-Null
    $ahkAsset = Get-GitHubZipAsset -Repository 'AutoHotkey/AutoHotkey' -Filter { $_.name -match '^AutoHotkey_.*\.zip$' }
    $compilerAsset = Get-GitHubZipAsset -Repository 'AutoHotkey/Ahk2Exe' -Filter { $_.name -match '\.zip$' }
    Invoke-Download -Uri $ahkAsset.browser_download_url -Destination '.build\AutoHotkey.zip'
    Invoke-Download -Uri $compilerAsset.browser_download_url -Destination '.build\Ahk2Exe.zip'
    Expand-Archive -LiteralPath '.build\AutoHotkey.zip' -DestinationPath '.build\ahk' -Force
    Expand-Archive -LiteralPath '.build\Ahk2Exe.zip' -DestinationPath '.build\compiler' -Force

    $compiler = Get-ChildItem -LiteralPath '.build\compiler' -Recurse -Filter 'Ahk2Exe.exe' | Select-Object -First 1
    $base = Get-ChildItem -LiteralPath '.build\ahk' -Recurse -Filter 'AutoHotkey64.exe' | Select-Object -First 1
    if (-not $compiler -or -not $base) {
        throw 'AutoHotkey compiler or 64-bit base executable was not found after download.'
    }
    return @{ Compiler = $compiler.FullName; Base = $base.FullName }
}

Write-Host 'Building remote agent...'
$goExe = Ensure-PortableGo
Push-Location remote\agent
try {
    & $goExe build -o animeexpedition-agent.exe .
    if ($LASTEXITCODE -ne 0) {
        throw "go build failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

Write-Host 'Building OCR helper...'
Push-Location ocr
try {
    python -m pip install -e '.[dev]'
    python -m PyInstaller --onefile --name ocr_server --distpath dist --workpath build --specpath build ocr_helper/cli.py
    if ($LASTEXITCODE -ne 0) {
        throw "OCR PyInstaller build failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}
$ocrOutputPath = Join-Path $repoRoot 'macro\ocr_server.exe'
Stop-ProcessesUsingFile -Path $ocrOutputPath
Copy-Item -LiteralPath 'ocr\dist\ocr_server.exe' -Destination $ocrOutputPath -Force

Write-Host 'Compiling AutoHotkey engine...'
$ahkTools = Ensure-AutoHotkeyTools
New-Item -ItemType Directory -Path 'dist' -Force | Out-Null
$enginePath = Join-Path $repoRoot 'dist\AEMEngine.exe'
$arguments = '/in "{0}" /out "{1}" /base "{2}" /icon "{3}"' -f `
    (Join-Path $repoRoot 'macro\tower_defense_macro_gui.ahk'), $enginePath, $ahkTools.Base, (Join-Path $repoRoot 'assets\app.ico')
Stop-ProcessesUsingFile -Path $enginePath
$process = Start-Process -FilePath $ahkTools.Compiler -ArgumentList $arguments -Wait -PassThru
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $enginePath)) {
    throw "Ahk2Exe failed with exit code $($process.ExitCode)."
}

Write-Host 'Packaging installer EXE...'
$versionPath = Join-Path $repoRoot 'VERSION'
$iconPath = Join-Path $repoRoot 'assets\app.ico'
$guiOutputPath = Join-Path $repoRoot 'gui\dist\gui.exe'
Stop-ProcessesUsingFile -Path $guiOutputPath
Push-Location gui
try {
    python -m pip install -e '.[dev]'
    $stylePath = (Resolve-Path 'app\style.qss').Path
    python -m PyInstaller --windowed --onefile --paths . `
        --add-data "$stylePath;." `
        --add-data "$versionPath;." `
        --add-binary "$enginePath;engine" `
        --icon "$iconPath" `
        --add-data "$iconPath;." `
        --name gui --distpath dist --workpath build --specpath build app/main.py
    if ($LASTEXITCODE -ne 0) {
        throw "GUI PyInstaller build failed with exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

$outputPath = Join-Path $repoRoot 'dist\Kimberlites-Macro-Menu.exe'
Stop-ProcessesUsingFile -Path $outputPath
Copy-Item -LiteralPath 'gui\dist\gui.exe' -Destination $outputPath -Force
if (-not (Test-Path -LiteralPath $outputPath)) {
    throw 'The final installer EXE was not created.'
}

if (-not $SkipSmokeTest) {
    Write-Host 'Smoke-testing installer EXE...'
    $env:QT_QPA_PLATFORM = 'offscreen'
    New-Item -ItemType Directory -Path 'gui\smoke-test-dir' -Force | Out-Null
    $process = Start-Process -FilePath (Resolve-Path 'gui\dist\gui.exe').Path `
        -ArgumentList '--dir', (Resolve-Path 'gui\smoke-test-dir').Path -WindowStyle Hidden -PassThru
    try {
        Start-Sleep -Seconds 5
        if ($process.HasExited) {
            throw "The built GUI exited unexpectedly with code $($process.ExitCode)."
        }
    } finally {
        if (-not $process.HasExited) {
            Stop-ProcessTree -ProcessId $process.Id
        }
    }
}

$sizeMiB = [math]::Round((Get-Item -LiteralPath $outputPath).Length / 1MB, 1)
Write-Host "Build complete: $outputPath ($sizeMiB MiB)"
