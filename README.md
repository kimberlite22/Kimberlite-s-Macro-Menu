# Kimberlite's Anime Expedition Macro

An AutoHotkey v2 GUI automation tool for the Roblox tower-defense game **Anime Expedition**. It
drives the game window through a configurable screen state machine — detecting on-screen states via
OCR, clicking buttons, dragging the camera, placing towers, and looping rounds automatically — so
you can idle/farm rounds without babysitting the game.

[![Latest release](https://img.shields.io/github/v/release/kimberlite22/Anime-Expedition-Macro-Menu)](https://github.com/kimberlite22/Anime-Expedition-Macro-Menu/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows-blue)](#requirements)
[![AutoHotkey v2](https://img.shields.io/badge/AutoHotkey-v2-green)](https://www.autohotkey.com/)

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Getting started](#getting-started)
- [Usage](#usage)
- [Configuration](#configuration)
- [Remote access](#remote-access-optional)
- [Repository layout](#repository-layout)
- [Development](#development)
- [Documentation](#documentation)

## Features

- **Screen state machine** — define screens (e.g. "Main Menu", "Round Start") and steps (click,
  drag, wait, capture) that drive the game automatically once a matching screen is detected.
- **OCR-based screen detection** — uses the Windows OCR engine (via a persistent PowerShell helper)
  to read on-screen text and decide which screen is currently active, with a fuzzy-match fallback
  tolerant of small OCR misreads.
- **Presets** — save, load, and queue full configurations (screens, steps, coordinates) per map or
  strategy; switch presets mid-run at the next cycle boundary without losing state.
- **Resolution-independent coordinates** — click and detection positions are stored as
  percent-of-window, not raw pixels, so a preset keeps working after moving or resizing the game
  window or switching monitors.
- **Disconnect detection & auto-reconnect** — recognizes a dropped connection and automatically
  restarts the run.
- **Automatic config backups** — timestamped backups of `config.ini` on save.
- **Optional remote access** — monitor status/logs and send a whitelisted set of safe commands
  (pause/resume/stop, switch preset) from a browser or phone. Fully opt-in and off by default; see
  [Remote access](#remote-access-optional).

## Requirements

- Windows 10 / 11
- For the recommended release EXE: no AutoHotkey installation required
- For running the source directly: [AutoHotkey v2.0](https://www.autohotkey.com/) (v1 will **not**
  run it)
- An English Windows OCR language pack (present on most systems by default)

## Getting started

1. Download `Kimberlites-Anime-Expedition-Macro.exe` from the
   [latest GitHub Release](https://github.com/kimberlite22/Anime-Expedition-Macro-Menu/releases/latest).
2. Double-click it once. The EXE installs the app for the current Windows user and opens it.
3. For future launches, press the Windows key and search for **Kimberlite's Anime Expedition Macro**.
4. On every launch, the installed app checks for a newer release before opening the macro. Updates
   are verified, installed in place, and preserve your configuration and backups.
5. Follow the **User Guide** (see [Documentation](#documentation)) — it walks through pinning the
   game window, capturing positions, building presets, and running the macro.

The installed files are kept in:

| Location | Contents |
|---|---|
| `%LocalAppData%\Programs\Kimberlite's Anime Expedition Macro` | EXE and bundled OCR helpers |
| `%LocalAppData%\Kimberlite's Anime Expedition Macro` | `config.ini`, backups, logs, and local bridge files |
| `%AppData%\Microsoft\Windows\Start Menu\Programs` | The Windows-searchable shortcut |

The originally downloaded EXE can be deleted after the first launch.

Developers can also install AutoHotkey v2 and run `macro/tower_defense_macro_gui.ahk` directly.
Source runs remain self-contained and do not install, create a shortcut, or check for updates.

## Usage

The GUI has three tabs: **Preset Settings**, **Map Placement**, and **General**.

| Hotkey | Action |
|---|---|
| `F7` | Toggle placement mode |
| `F8` | Capture a position at the current cursor location |
| `F9` | Pause / resume the macro |
| `F10` | Start the macro |
| `Escape` | Emergency stop (or cancel an in-progress capture) |

The typical workflow is: pin the game window in **General**, build/capture screens and steps for
your map in **Preset Settings** / **Map Placement**, then press `F10` to run. Full step-by-step
instructions are in the [User Guide](#documentation).

## Configuration

All settings — presets, screens, and steps — live in `config.ini` next to the installed app (see the
table above), encoded as UTF-16LE. It is user-local and not tracked in this repository. Every save
writes a timestamped backup to `config_backups/` alongside it.

## Remote access

An optional companion system lets you monitor the macro (live status, logs) and send a small
whitelisted set of safe commands (pause / resume / stop, switch preset) from a browser or phone,
without opening any inbound ports on your PC:

```
[Browser / phone] --HTTPS--> [Cloud backend + website] <--outbound-- [Local agent] <--files--> [AHK macro]
```

- The macro itself does **no networking** — it only reads/writes local files. All networking and
  auth live in a separate local agent (`remote/agent/`, Go) and backend (`remote/server/`).
- It's off by default, toggled via the "Enable remote bridge" checkbox on the **General** tab, and
  can be fully paired from the macro's own "Remote Agent Setup..." window — no terminal required.
- See [`remote/README.md`](remote/README.md) for setup, [`remote/PROTOCOL.md`](remote/PROTOCOL.md)
  for the wire contract, and [`remote/DEPLOY.md`](remote/DEPLOY.md) for production deployment.

## Repository layout

- **`macro/`** — the application and all its runtime files.
  - `tower_defense_macro_gui.ahk` — the whole application (AutoHotkey v2): GUI, state machine,
    input, OCR client, config load/save.
  - `ocr_server.ps1` — persistent OCR helper used while the macro runs.
  - `ocr_region.ps1` — one-shot region OCR helper.
  - `remote_bridge.ahk` — optional local module for the remote access feature (off by default).
  - `config.ini` (user-local, gitignored) and `config_backups/` — settings and automatic backups.
- **`remote/`** — the optional remote access agent (`agent/`, Go) and backend + web UI
  (`server/`, Node + Fastify). See [Remote access](#remote-access-optional). The web UI also hosts
  the User Guide as its Documentation tab (see [Documentation](#documentation)).
- **`tools/`** — repository maintenance scripts.

## Development

Source runs directly with AutoHotkey v2 — no build step:

1. Install [AutoHotkey v2.0](https://www.autohotkey.com/).
2. Open `macro/tower_defense_macro_gui.ahk` (double-click, or run it from a terminal).

To work on the optional remote access system, see the "Quick start" section in
[`remote/README.md`](remote/README.md) (requires Node.js and Go).

## Documentation

The full **User Guide** is the Documentation tab of the remote access web UI
([`remote/server/web/index.html`](remote/server/web/index.html)) — it covers pinning the game window,
capturing positions, building presets, running the macro end to end, and setting up remote access.
The Documentation tab is static and needs no backend or account, so you can open that file directly
in a browser even without running the server; once the remote access site is deployed (see
[`remote/DEPLOY.md`](remote/DEPLOY.md)), the same tab is reachable at its hosted URL.
