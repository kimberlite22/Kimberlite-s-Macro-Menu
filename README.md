# Anime Expedition Macro Menu

An AutoHotkey v2 GUI automation tool for the Roblox tower-defense game **Anime Expedition**.
It drives the game window through a configurable screen state machine: detecting on-screen states
via OCR, clicking buttons, dragging the camera, placing towers, and looping rounds automatically.

## Repository layout

- **`macro/`** — the application and all its runtime files.
  - `tower_defense_macro_gui.ahk` — the whole application (AutoHotkey v2).
  - `ocr_server.ps1`, `ocr_region.ps1` — Windows OCR helpers.
  - `config.ini` (user-local) and `config_backups/` — settings and automatic backups.
- **`website/`** — self-contained documentation site (the user guide).
  - `website/index.html` — open it in any browser, or host the `website/` folder (e.g. GitHub Pages).

## Requirements

- Windows 10 / 11
- [AutoHotkey v2.0](https://www.autohotkey.com/) (v1 will not run the script)
- An English Windows OCR language pack (present on most systems)

## Getting started

1. Install AutoHotkey v2.
2. Double-click `macro/tower_defense_macro_gui.ahk`.
3. Follow the **User Guide** in `website/index.html` — it walks through pinning the game window,
   capturing positions, building presets, and running the macro.

## Hotkeys

`F7` placement mode · `F8` capture position · `F9` pause/resume · `F10` start · `Esc` emergency stop
