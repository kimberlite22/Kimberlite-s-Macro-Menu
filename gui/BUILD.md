# Building gui.exe

This folder contains the PySide6 presentation process for Kimberlite's Anime
Expedition Macro. The executable is a standalone build of the GUI only.

## Dev setup

```
cd gui
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

## Running the tests

```
pytest
```

The tests set `QT_QPA_PLATFORM=offscreen` in `tests/conftest.py`, so they do
not open a visible window or require the AHK application to run.

## Building the executable

```
cd gui
pyinstaller --windowed --onefile --paths . --add-data "app/style.qss;." --name gui --distpath dist --workpath build --specpath build app/main.py
```

`--windowed` is PyInstaller's no-console mode for a Windows GUI application.
This produces `gui/dist/gui.exe`. It is a build artifact, not committed source.

Two flags matter here and were verified by actually building and running the
result, not just by reading the command - both failed silently otherwise:

- `--paths .` - without it, PyInstaller's static import analysis (starting
  from `app/main.py`) never discovers `app`/`ipc` as importable top-level
  packages (they're only found at runtime via `main.py`'s own `sys.path`
  manipulation, which PyInstaller's analysis pass doesn't execute) - the
  built exe launches and immediately crashes with
  `ModuleNotFoundError: No module named 'app'`.
- `--add-data "app/style.qss;."` (destination `.`, NOT `app`) - PyInstaller's
  onefile bootloader resolves the frozen entry script's `__file__` at the
  bundle ROOT, not under an `app/` subfolder, so `main.py`'s existing
  `Path(__file__).with_name("style.qss")` lookup only finds it there.
  Bundling it under `app/` (matching the source tree's own layout) instead
  produces a working build that still crashes with
  `FileNotFoundError` the moment it tries to load the stylesheet.

If invoking a relative `--add-data` source path ever fails with "Unable to
find ... when adding binary and data files" pointing at a path prefixed with
`build\` (PyInstaller resolving the datas path relative to `--specpath`
rather than the current directory in some versions/invocations), pass an
absolute path for the source side of `--add-data` instead.

## Verifying the standalone build works

Use a temporary data directory. A real `config.ini` is not needed because the
main window handles a missing file gracefully:

```
mkdir smoke-test-dir
dist\gui.exe --dir smoke-test-dir
```

For automated or CI-style smoke testing, use the offscreen Qt platform. The GUI
has no one-shot mode, so the useful automated proof is that the build succeeds
and the executable launches without an error. Keep the launch bounded, then
stop the test process because the normal GUI is expected to keep running:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
New-Item -ItemType Directory -Path smoke-test-dir -Force | Out-Null
$process = Start-Process -FilePath '.\dist\gui.exe' -ArgumentList '--dir', 'smoke-test-dir' -PassThru
try {
  Start-Sleep -Seconds 3
  if ($process.HasExited) { throw "gui.exe exited unexpectedly with code $($process.ExitCode)." }
} finally {
  if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
}
```

Visual inspection remains a manual side-by-side step. This follows the migration
milestones' no-AHK/game verification approach: packaging can be proven without
starting the macro application or Roblox.

## What this build does NOT do yet

This build does not embed or launch the AHK engine executable. It only proves
that the separate Python GUI can be packaged and started standalone. It is not
the primary release executable and is not uploaded as a GitHub Release asset.

The repository-root `VERSION` file is a forward-looking marker for sharing
version stamps between Ahk2Exe and PyInstaller. It is not consumed by this build
or the release workflow yet.
