# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Hard rules (always follow)

- **Everything in English.** All code, comments, GUI text, tooltips, log messages, and
  documentation must be written in English — even when the user chats in another language.
- **Do NOT open / run the AHK application while testing.** Never launch
  `tower_defense_macro_gui.ahk` (or otherwise start the macro on screen) as part of testing or
  verifying changes. The only exception is when the user explicitly says it is currently OK to
  run it ("it's fine right now" / "go ahead and open it"). Verify changes by reading the code
  and reasoning about it instead.

## Project overview

Anime Expedition Macro Menu — an AutoHotkey v2 GUI automation tool for the Roblox tower-defense
game "Anime Expedition". It drives the game window through a configurable screen state machine:
detecting on-screen states (via OCR), clicking buttons, dragging the camera, placing towers, and
looping rounds automatically.

## Layout

- `tower_defense_macro_gui.ahk` — the whole application (~5000 lines, AutoHotkey v2). GUI, state
  machine, input, OCR client, config load/save.
- `config.ini` — all settings, presets, screens and steps. **UTF-16LE**, gitignored (user-local).
- `config_backups/` — timestamped automatic backups of `config.ini`.
- `ocr_server.ps1` — persistent OCR helper. Loads the WinRT OCR engine once and services scan
  requests over a small file-based protocol (`ocr_req.txt` / `ocr_resp.txt` / `ocr_ready.txt` /
  `ocr_stop.txt`), so startup cost is paid once per session.
- `ocr_region.ps1` — one-shot region OCR helper.
- `macro_log.txt`, `ocr_result*.txt` — runtime log / OCR output files.

## Key conventions (read before editing)

- **Coordinates are stored as percent-of-opening**, not raw screen pixels. The game window is
  pinned into a fixed "opening" rectangle (General / Game Window tab); every click and detection
  corner is a percentage (0–100) of that opening so presets survive moving/resizing/monitor
  changes. The opening's own geometry (`HoleX/Y/W/H`) stays in absolute pixels — it is the
  reference frame. Convert with `PctXFromAbs` / `PctYFromAbs` (store) and `AbsXY` (read).
- **One-time config migration.** `MigrateCoordsToPercent()` converts legacy absolute-pixel configs
  to percent once, then stamps `[General] CoordFormat=percent`. It is type-aware (e.g. a "Zoom Out"
  step keeps a wheel-tick count in X and must not be converted). Runs before any value is read.
- **`SendMode "Event"`** is deliberate — the game ignores the default SendInput mode. Do not change
  it. ("Play" mode failed to move the cursor at all on the target system.)
- **Lenient numeric parsing.** Use `SafeInt` / `SafeNum` for user-entered numbers; they trim
  whitespace and accept a comma as a decimal separator (German locale) instead of crashing.

## GUI tabs & hotkeys

- Tabs: **Preset Settings**, **Map Placement**, **General**.
- Hotkeys: `F7` placement mode, `F8` capture position at cursor, `F9` pause/resume,
  `F10` start macro, `Escape` emergency stop / cancel capture.
