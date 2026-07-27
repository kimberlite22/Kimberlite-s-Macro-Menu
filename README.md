# Kimberlite's Anime Expedition Macro

An AutoHotkey v2 GUI automation tool for the Roblox tower-defense game **Anime Expedition**.
It drives the game window through a configurable screen state machine: detecting on-screen states
via OCR, clicking buttons, dragging the camera, placing towers, and looping rounds automatically.

## Repository layout

- **`macro/`** — the application and all its runtime files.
  - `tower_defense_macro_gui.ahk` — the whole application (AutoHotkey v2).
  - `ocr_server.ps1`, `ocr_region.ps1` — Windows OCR helpers.
  - `config.ini` (user-local) and `config_backups/` — settings and automatic backups.
- **`website/`** — self-contained documentation site (the user guide).

## Requirements

- Windows 10 / 11
- For the recommended release EXE: no AutoHotkey installation required
- For running the source directly: [AutoHotkey v2.0](https://www.autohotkey.com/) (v1 will not run it)
- An English Windows OCR language pack (present on most systems)

## Getting started

1. Download `Kimberlites-Anime-Expedition-Macro.exe` from the latest GitHub Release.
2. Double-click it once. The EXE installs the app for the current Windows user and opens it.
3. For future launches, press the Windows key and search for **Kimberlite's Anime Expedition Macro**.
4. On every launch, the installed app checks for a newer release before opening the macro. Updates
   are verified, installed in place, and preserve the configuration and backups.
5. Follow the **User Guide** in `website/index.html` — it walks through pinning the game window,
   capturing positions, building presets, and running the macro.

The installed files are kept in:

- `%LocalAppData%\Programs\Kimberlite's Anime Expedition Macro` — EXE and bundled OCR helpers
- `%LocalAppData%\Kimberlite's Anime Expedition Macro` — `config.ini`, backups, logs, and local bridge files
- `%AppData%\Microsoft\Windows\Start Menu\Programs` — the Windows-searchable shortcut

The originally downloaded EXE can be deleted after the first launch.

Developers can still install AutoHotkey v2 and run `macro/tower_defense_macro_gui.ahk` directly.
Source runs remain self-contained and do not install, create a shortcut, or check for updates.

## Publishing a release

1. Change `AppVersion` near the top of `macro/tower_defense_macro_gui.ahk`.
2. Commit and push the change.
3. Create and push a matching tag, for example:

   ```powershell
   git tag v0.3.0
   git push origin v0.3.0
   ```

The release workflow downloads the official AutoHotkey v2 compiler, builds the Windows app EXE,
generates updater metadata with a SHA-256 checksum, and publishes only those runtime files as
GitHub Release assets. The website continues to deploy independently through GitHub Pages.

To customize the Windows app icon, add a real multi-resolution ICO file at `assets/app.ico`. The
release workflow detects it automatically and embeds it into the compiled EXE.
