# Building gui.exe

This folder contains the PySide6 presentation process for Kimberlite's Anime
Expedition Macro. `gui.exe` is the single installer/application executable
shipped in each GitHub Release: launched with no arguments, it self-installs
to the per-user `%LOCALAPPDATA%\Programs\<AppName>` location, creates the
Start Menu shortcut, extracts the AHK engine embedded inside its own bundle,
and launches that engine hidden in the background - the user only ever sees
this Python window. See `gui/app/self_install.py`/`engine_process.py`.

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

The real release build (`.github/workflows/release.yml`) also embeds the
compiled AHK engine exe and the repo-root `VERSION` file. Build the engine
first (compile `macro/tower_defense_macro_gui.ahk` with `Ahk2Exe`, after
building `macro/ocr_server.exe` and `remote/agent/animeexpedition-agent.exe`
so its own `FileInstall` calls succeed - see the repo root README/CLAUDE.md),
then:

```
cd gui
pyinstaller --windowed --onefile --paths . --add-data "app/style.qss;." --add-data "../VERSION;." --add-binary "<path-to-compiled-engine.exe>;engine" --name gui --distpath dist --workpath build --specpath build app/main.py
```

A plain build without `--add-binary` (just `--add-data "app/style.qss;."`)
still works for GUI-only development/testing - `gui.exe` degrades gracefully
to "Engine offline" if it can't find a bundled or dev-mode engine (see
`engine_process.find_engine_executable`).

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

## What this build does and does not do

`gui.exe` embeds and launches the AHK engine, self-installs, and creates the
Start Menu shortcut - but only for a real frozen launch with NO `--dir`
argument (an explicit `--dir`, as used by the smoke test above and by any
fixture-driven dev testing, is a deliberate escape hatch that skips all of
that and just points the GUI at the given directory's existing bridge files,
exactly like the pre-installer-era build did). The release workflow
(`.github/workflows/release.yml`) builds `gui.exe` this way and uploads it,
renamed to `Kimberlites-Anime-Expedition-Macro.exe`, as the release's only
executable asset - there is no separate AHK-engine-only download anymore.

`gui.exe` does NOT yet self-update (download-and-replace itself when a newer
release is available) - it only does a best-effort, non-blocking version
check against `update.ini` and shows a notice (`gui/app/update_check.py`).
Porting the AHK exe's actual self-replace mechanism is a deliberate follow-up.

The repository-root `VERSION` file is bundled into the frozen build (see the
`--add-data "../VERSION;."` flag above) and read by `update_check.py` to know
the running app's own version for that comparison.
