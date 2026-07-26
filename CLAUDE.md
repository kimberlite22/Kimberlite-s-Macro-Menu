# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Hard rules (always follow)

- **Everything in English.** All code, comments, GUI text, tooltips, log messages, and
  documentation must be written in English — even when the user chats in another language.
- **No emojis.** Never use emojis in anything that reaches the application (code, GUI text,
  tooltips, log messages) or in how Codex output and reasoning are presented (headings, section
  labels, findings). Use plain text labels only. This holds even when the user chats with emojis.
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

The repository is split into two top-level folders: `macro/` (the application and all its runtime
files) and `website/` (the static documentation site). All macro file paths below are relative to
`macro/`; the application resolves them via `A_ScriptDir`, so every file it reads/writes lives next
to `tower_defense_macro_gui.ahk` inside `macro/`.

- `macro/tower_defense_macro_gui.ahk` — the whole application (~5000 lines, AutoHotkey v2). GUI,
  state machine, input, OCR client, config load/save.
- `macro/config.ini` — all settings, presets, screens and steps. **UTF-16LE**, gitignored
  (user-local).
- `macro/config_backups/` — timestamped automatic backups of `config.ini`.
- `macro/ocr_server.ps1` — persistent OCR helper. Loads the WinRT OCR engine once and services scan
  requests over a small file-based protocol (`ocr_req.txt` / `ocr_resp.txt` / `ocr_ready.txt` /
  `ocr_stop.txt`), so startup cost is paid once per session.
- `macro/ocr_region.ps1` — one-shot region OCR helper.
- `macro/macro_log.txt`, `macro/ocr_result*.txt` — runtime log / OCR output files.
- `website/` — self-contained static documentation site (user guide). `website/index.html` is the
  entry point; no build step or external dependencies.

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

## Codex delegation

For subtasks with low reasoning demand (simple bug fixes, boilerplate code, simple refactors,
writing tests, repetitive changes), delegate the implementation to Codex instead of writing it
yourself. Use the repo wrapper `tools/codex-delegate.mjs` (it runs `codex exec --json` and surfaces
Codex's full reasoning trace, which the `/codex:rescue` plugin command drops):

    node tools/codex-delegate.mjs --model gpt-5.6-luna --effort low "<concrete, clearly scoped task>"

It runs Codex in the workspace-write sandbox so Codex can implement the change; add `--read-only`
for investigations that must not touch files. The wrapper streams Codex's full reasoning live, line
by line, into a per-model Markdown file in the repo root (`codex-reasoning-<model>.md`, gitignored;
override with `--reasoning-file <path>`). Each file opens its own VS Code tab the moment it receives
its first thought-process update, if not already open (`code -r`, best-effort; per model,
independently; use `--no-open` to skip). New runs APPEND a new dated section — previous thought
processes are kept;
delete the file to clear it. If that file is already held by another running instance, the run
streams to a separate temp file instead (also opened in VS Code), so simultaneous runs never
interleave. The open tab live-updates as reasoning streams (or `tail -f` it). To stdout, and thus into this chat, the wrapper prints only the
final answer plus the reasoning-file path. Relay that answer and the path as-is; do NOT paste the
reasoning into the chat. After a workspace-write run, check `git status` / `git diff` to see what
Codex changed, then review it (below).

Do NOT use this for: architecture decisions, complex logic, security-relevant code (auth, data
processing, payments), or anything where a mistake would be costly. Implement those yourself.

After completing EVERY subtask (delegated or implemented yourself), get a second opinion. Run the
review through the SAME wrapper with `--read-only`, so the review's reasoning also streams live to
the reasoning file (watchable, and kept out of the chat). Pick the model and scope by the review's
role:

- Per-subtask review (trivial) — lighter model at low effort, scoped to ONLY the file(s) the subtask
  changed (get them from `git status`). Review the change, not the whole file:

      node tools/codex-delegate.mjs --read-only --model gpt-5.6-terra --effort low "Review the CHANGES to <the changed file(s)> and their immediate context. Focus on what the subtask added or modified; do NOT re-report unrelated pre-existing code. Report issues with file:line; if none, say it looks good. Do not modify files."

- Change-focused review (non-trivial / final) — stronger model at high effort, over ALL uncommitted
  changes and their context (still the diff, not whole files, so it does not keep re-reporting the
  same pre-existing issues in unchanged code):

      node tools/codex-delegate.mjs --read-only --model gpt-5.6-sol --effort high "Review the uncommitted CHANGES and their surrounding context - not entire files. Use git -c safe.directory='*' status --short and git -c safe.directory='*' diff to see exactly what changed (read new untracked files directly). Comment only on the changed lines and directly-related context; do NOT re-report pre-existing issues in unchanged code. Report the most important issues with file:line, prioritized. Do not modify files."

The `git -c safe.directory='*'` prefix is required because the Codex sandbox runs as a different OS
user and plain git otherwise aborts with "dubious ownership". Summarize the review's answer (the
findings) in the chat; its reasoning streams to the reasoning file, not the chat. Codex is
configured for detailed + raw reasoning (`model_reasoning_summary = "detailed"`,
`show_raw_agent_reasoning = true` in `~/.codex/config.toml`).

The native `codex exec review --uncommitted -c model="…"` reviewer is an alternative that yields
more structured P1/P2 findings, but it cannot scope to a single file and does not stream reasoning
to the reasoning file. Note: `codex exec review` cannot combine `--uncommitted` with a focus prompt.

When enabled, the stop-time review gate also runs a final `/codex:review` on the global default
(`gpt-5.6-sol` / `high`) before each turn ends. (`/codex:setup --enable-review-gate` /
`--disable-review-gate` toggles it.)

### Presenting Codex output

When relaying Codex output into the chat, render it as clean Markdown — never paste the raw runtime
log:

- Drop the transient `[codex] Running command: …` / `[codex] Command completed …` command-execution
  progress lines — those are runtime noise.
- Reasoning placement: delegation AND reviews both run through `tools/codex-delegate.mjs`, which
  streams reasoning to the reasoning file, NOT the chat. In the chat, relay only the wrapper's
  answer (findings) and the reasoning-file path. (If you fall back to the native `codex exec review`,
  its reasoning renders inline as a `Reasoning:` section — surface that under a plain **Reasoning**
  heading, no emoji.)
- Render the final answer / review findings as normal Markdown (headings, bullet lists, fenced code,
  `file:line` links).
- Keep the substance of reasoning and findings verbatim — do not paraphrase or shorten it; only the
  runtime progress log may be omitted.

For a live, terminal-native "thinking" stream, the user can also run Codex interactively (`codex`
with no subcommand) in a real terminal — the TUI renders reasoning as it streams — or watch the
delegation reasoning file live (VS Code preview / `tail -f`).
