# Kimberlite's Macro Menu

A Windows automation tool for the Roblox tower-defense game **Anime Expedition**: a PySide6 (Qt)
window in front of an AutoHotkey v2 engine. It drives the game window through a configurable screen
state machine: detecting on-screen states via OCR, clicking buttons, dragging the camera, placing
towers, and looping rounds automatically, so you can idle/farm rounds without babysitting the game.

[![Latest release](https://img.shields.io/github/v/release/kimberlite22/Kimberlite-s-Macro-Menu)](https://github.com/kimberlite22/Kimberlite-s-Macro-Menu/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows-blue)](#requirements)
[![AutoHotkey v2](https://img.shields.io/badge/engine-AutoHotkey%20v2-green)](https://www.autohotkey.com/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-blue)](https://doc.qt.io/qtforpython-6/)

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Getting started](#getting-started)
- [Usage](#usage)
- [Background session](#background-session)
- [Configuration](#configuration)
- [Remote access](#remote-access)
- [Repository layout](#repository-layout)
- [Development](#development)
- [Documentation](#documentation)

## Features

- **Screen state machine**: define screens (e.g. "Main Menu", "Round Start") and steps (click,
  drag, wait, capture) that drive the game automatically once a matching screen is detected.
- **OCR-based screen detection**: reads on-screen text with the Windows OCR engine through a
  bundled helper process and decides which screen is currently active. Matching is scored rather
  than exact, so small OCR misreads (o/0, l/1, i/1, s/5, b/8) and line breaks inside a region still
  match, and a detection that misses logs the score it reached.
- **Presets**: save, load, and queue full configurations (screens, steps, coordinates) per map or
  strategy; switch presets mid-run at the next cycle boundary without losing state.
- **Resolution-independent coordinates**: click and detection positions are stored as
  percent-of-window, not raw pixels, so a preset keeps working after moving or resizing the game
  window or switching monitors.
- **Live stats**: run counters, per-screen timings, and the macro log in their own tab, so nothing
  has to be drawn over the game window.
- **Disconnect detection and auto-reconnect**: recognizes a dropped connection and automatically
  restarts the run.
- **Private server auto-join**: joins a configured private server link through Roblox' own
  `roblox://` handler, so no browser is involved. If that route fails, it falls back to opening the
  link normally and closes the browser it started once Roblox is up.
- **Optional background session**: run the macro in a second Windows session so the game does not
  occupy your desktop; see [Background session](#background-session).
- **Optional remote access**: monitor status/logs and send a whitelisted set of safe commands
  (pause/resume/stop, switch preset) from a browser or phone. Fully opt-in and off by default; see
  [Remote access](#remote-access).
- **Automatic config backups**: timestamped backups of `config.ini` on save.
- **Self-update**: the installed app checks for a newer release on startup and can download,
  verify, and install it after a confirmation prompt.

## Requirements

- Windows 10 / 11
- An English Windows OCR language pack (present on most systems by default)
- For the release EXE: nothing else. AutoHotkey and Python are not needed; both the engine and the
  OCR helper ship inside the download.
- For running from source: [AutoHotkey v2.0](https://www.autohotkey.com/) (v1 will **not** run the
  engine) and Python 3.10+ for the GUI and the OCR helper; see [Development](#development).
- For the optional background session: RDP Wrapper, plus Remote Desktop enabled for the account.

## Getting started

1. Download `Kimberlites-Macro-Menu.exe` from the
   [latest GitHub Release](https://github.com/kimberlite22/Kimberlite-s-Macro-Menu/releases/latest).
2. Double-click it once. The EXE installs the app for the current Windows user, extracts the
   engine and helper processes it needs, and opens the window.
3. For future launches, press the Windows key and search for **Kimberlite's Macro Menu**.
4. On startup, the app does a quick, non-blocking check for a newer release. If one exists, it
   offers to install it: the new EXE is downloaded, checked against the release's published
   SHA-256, and only then swapped in, after which the app restarts itself. Declining leaves a
   notice in the window and asks again next start.
5. Follow the **User Guide** (see [Documentation](#documentation)); it walks through pinning the
   game window, capturing positions, building presets, and running the macro.

The installed files are kept in:

| Location | Contents |
|---|---|
| `%LocalAppData%\Programs\Kimberlite's Macro Menu` | The app EXE, the AHK engine, and the bundled helpers |
| `%LocalAppData%\Kimberlite's Macro Menu` | `config.ini`, backups, logs, OCR samples, and bridge files |
| `%AppData%\Microsoft\Windows\Start Menu\Programs` | The Windows-searchable shortcut |

The originally downloaded EXE can be deleted after the first launch.

Only a real installed launch installs and self-updates. Running the EXE with an explicit `--dir`
argument, or running from source, points the app at that directory's existing files and skips
installation, the shortcut, and the update install.

## Usage

The window has six tabs:

| Tab | What it is for |
|---|---|
| **Presets** | Screens, steps, and preset management: the macro's actual behavior |
| **Map Placement** | Tower placement positions and per-map options |
| **Live Stats** | Run counters, per-screen timings, and the macro log |
| **General** | Game window pinning, detection settings, and global options |
| **Remote Agent** | Pairing and controls for the optional remote access agent |
| **Background Session** | Setup and control of the optional hidden Windows session |

A search box above the tabs finds an individual setting by name and jumps to it.

| Hotkey | Action |
|---|---|
| `F7` | Pin the game window into the opening |
| `F8` | Capture a position at the current cursor location |
| `F9` | Pause / resume the macro |
| `F10` | Start the macro |
| `Escape` | Emergency stop (or cancel an in-progress capture) |

The typical workflow is: pin the game window in **General**, build/capture screens and steps for
your map in **Presets** / **Map Placement**, then press `F10` to run. Full step-by-step
instructions are in the [User Guide](#documentation).

The AutoHotkey engine runs hidden behind this window and owns the input simulation, the state
machine, and `config.ini`. In the shipped app it has no interface of its own; everything goes
through the tabs above.

## Background session

Optional, and off unless you set it up. Windows client editions normally allow one interactive
session per user, so a running macro occupies your desktop. With RDP Wrapper installed, the
**Background Session** tab creates a second session for the same account and starts the game and
the macro inside it, leaving your own desktop free. The tab reports each prerequisite separately
(Remote Desktop enabled, a second session allowed, RDP Wrapper loaded, a matching `rdpwrap.ini`
section) so a missing piece is visible rather than a silent failure.

Two things to know before relying on it. A disconnected session has no rendered desktop, so screen
detection can stop until you press **Show** again; check the macro log before leaving a long run
disconnected. And both sessions share one Windows profile, so never run two macro instances at the
same time.

## Configuration

All settings (presets, screens, and steps) live in `config.ini` in the data directory (see the
table above), encoded as UTF-16LE. It is user-local and not tracked in this repository. Every save
writes a timestamped backup to `config_backups/` alongside it.

Coordinates are stored as percent of the pinned game window, so a preset survives moving or
resizing that window. Legacy absolute-pixel configs are migrated once, automatically.

## Remote access

An optional companion system lets you monitor the macro (live status, logs) and send a small
whitelisted set of safe commands (pause / resume / stop, switch preset) from a browser or phone,
without opening any inbound ports on your PC:

```
[Browser / phone] --HTTPS--> [Cloud backend + website] <--outbound-- [Local agent] <--files--> [AHK macro]
```

- The macro itself does **no networking**; it only reads/writes local files. All networking and
  auth live in a separate local agent (`remote/agent/`, Go) and backend (`remote/server/`).
- It is off by default, toggled via the "Enable remote bridge" checkbox on the **Remote Agent**
  tab, and can be fully paired from that same tab; no terminal required.
- See [`remote/README.md`](remote/README.md) for setup, [`remote/PROTOCOL.md`](remote/PROTOCOL.md)
  for the wire contract, and [`remote/DEPLOY.md`](remote/DEPLOY.md) for production deployment.

## Repository layout

- **`gui/`**: the PySide6 presentation process, built into the single executable each release
  ships. `app/` holds the main window, the tabs, and the secondary windows; `ipc/` holds the
  local bridge client that talks to the engine; `tests/` is a pytest suite. See `gui/BUILD.md`.
- **`macro/`**: the AutoHotkey v2 engine and all its runtime files.
  - `tower_defense_macro_gui.ahk`: the engine (state machine, input simulation, OCR client,
    config load/save).
  - `ocr_matching.ahk`: the single scoring rule that decides whether an OCR read matches an
    expected text, with its own test file under `macro/tests/`.
  - `local_bridge.ahk` and `remote_bridge.ahk`: the file-based channels to the GUI (always on) and
    to the remote agent (off by default).
  - `ocr_server.exe`: the OCR helper, built from `ocr/`. Not committed (build artifact).
  - `config.ini` (user-local, gitignored) and `config_backups/`: settings and automatic backups.
- **`ocr/`**: the OCR helper's Python source (`ocr_helper/`), tests, and `BUILD.md` for building
  `macro/ocr_server.exe` with PyInstaller.
- **`remote/`**: the optional remote access agent (`agent/`, Go) and backend plus web UI
  (`server/`, Node + Fastify). See [Remote access](#remote-access). The web UI also hosts
  the User Guide as its Documentation tab (see [Documentation](#documentation)).
- **`tasklist/`**: the backlog, one Markdown file per task, plus generated indexes.
- **`tools/`**: repository maintenance and build scripts.
- **`.github/workflows/`**: CI plus the release workflow that builds and publishes the EXE.

## Development

The release EXE is built from three parts, so a source checkout needs a one-time build of the
helpers it uses. Step 2 is what OCR detection needs; step 3 is only for remote access:

1. Install [AutoHotkey v2.0](https://www.autohotkey.com/) and Python 3.10+.
2. Build the OCR helper once: follow `ocr/BUILD.md`, then copy the resulting
   `ocr/dist/ocr_server.exe` to `macro/ocr_server.exe`. Without it, OCR detection does nothing.
3. Optional, only for remote access: build the agent with `go build -o animeexpedition-agent.exe .`
   in `remote/agent/`.
4. Set up the GUI: `cd gui`, then `pip install -e .[dev]` (a virtualenv is recommended), and run it
   with `python app/main.py`. `pytest` runs the GUI suite offscreen, with no game or engine needed.

To run only the engine, open `macro/tower_defense_macro_gui.ahk` directly; its own AutoHotkey GUI
still exists and is shown when it is started this way, though the shipped app never displays it.

A full local installer build is available through `tools/build-local-exe.ps1` (also a VS Code build
task); it downloads its portable Go and AutoHotkey toolchains as needed and writes
`dist\Kimberlites-Macro-Menu.exe`. It creates no tag and no GitHub release.

To work on the optional remote access system, see the "Quick start" section in
[`remote/README.md`](remote/README.md) (requires Node.js and Go).

## Documentation

The full **User Guide** is the Documentation tab of the remote access web UI
([`remote/server/web/index.html`](remote/server/web/index.html)); it covers pinning the game window,
capturing positions, building presets, running the macro end to end, and setting up remote access.
The Documentation tab is static and needs no backend or account, so you can open that file directly
in a browser even without running the server; once the remote access site is deployed (see
[`remote/DEPLOY.md`](remote/DEPLOY.md)), the same tab is reachable at its hosted URL.
