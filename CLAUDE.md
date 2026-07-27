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
- `macro/remote_bridge.ahk` — optional local "remote bridge" module, `#Include`d at the very end of
  `tower_defense_macro_gui.ahk`. Off by default. When enabled it writes a status snapshot and reads a
  whitelisted command file so an out-of-process agent can observe/control the macro WITHOUT any
  networking code in the AHK app. See "Remote access initiative" below.
- `macro/remote_status.json` / `macro/remote_cmd.txt` / `macro/remote_ack.txt` (+ `.tmp`) — runtime
  files for the remote bridge; all gitignored, regenerated at runtime.
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

## Remote access initiative (in progress)

Long-term goal: a website with user accounts that gives remote access to the macro — view logs and
live status, and issue a small set of safe controls (pause / resume / stop, pick or queue the next
preset). Decided scope: reachable from anywhere over the internet, and multi-tenant (many independent
users, each running their own macro + agent). This section is the shared context for that effort so
any chat can pick it up.

### Target architecture (3-layer phone-home)

    [Browser / phone] --HTTPS--> [Cloud backend + website] <--outbound-- [Local agent] <--files--> [AHK macro]
       (user login)              (accounts, API, DB)         (only net I/O)  (Go, single .exe)   (this repo)

- The home PC only ever makes OUTBOUND connections (the agent "phones home"). No port forwarding, no
  inbound firewall holes.
- The AHK macro does NO networking. It only reads/writes local files (the remote bridge, below),
  exactly like the OCR helper. All networking and auth live in the agent and the cloud backend.
- Recommended stack (NOT built yet): Go agent (single `.exe`, no runtime dependency); TypeScript
  backend (Node + Fastify) + frontend sharing the command enum as one type; PostgreSQL; a mature auth
  library (e.g. better-auth / Auth.js) with TOTP 2FA; TLS via Caddy auto-HTTPS or a Cloudflare Tunnel.

### Security model (non-negotiable)

- The command channel is UNTRUSTED input. It may ONLY trigger a fixed whitelist of predefined actions
  — never raw coordinates, keystrokes, scripts, or arbitrary preset data. Validate every field against
  existing state before acting (e.g. a preset name must already exist).
- Outbound-only from the home PC; device-specific, revocable pairing tokens (separate from the user
  login); TLS everywhere; rate limiting plus an audit log of remote actions. Do NOT hand-roll auth or
  crypto (this is exactly the "security-relevant code" the Codex rules say to implement carefully).
- Known risks to weigh before going multi-user: a public service that helps many people automate a
  Roblox game very likely violates Roblox ToS and can get users' accounts banned; and the agent `.exe`
  should be code-signed (Windows SmartScreen + user trust).

### Phase 0 — local bridge (DONE, `macro/remote_bridge.ahk`)

Network-free foundation. Off by default via the "Enable remote bridge" checkbox (General tab, bottom
strip), persisted to `[General] RemoteBridgeEnabled`; the checkbox is the live source of truth (read
each tick, like `disconnectEnabledChk`). File protocol in `A_ScriptDir`, mirroring the OCR helper
(atomic `.tmp` + `FileMove`, a request token, consume-on-read):

- `remote_status.json` — macro writes ~1x/sec; the `timestamp` field doubles as a heartbeat (stale =
  offline). Includes run state, active/running/queued preset, current map/screen/step, and counters.
- `remote_cmd.txt` — the agent writes one command `<token>|<TYPE>|<arg>` (atomic-published); the macro
  consumes (deletes) it on read, so each command runs at most once.
- `remote_ack.txt` — macro writes `<token>|<ok|error>|<message>` so the agent can confirm each command.
- Logs are NOT duplicated into status; the agent tails `macro_log.txt` directly.

Command whitelist (each maps onto the SAME mechanism a local hotkey/button uses, so a remote command
can never do more than a local key press): `PAUSE`, `RESUME`, `STOP`,
`SET_ACTIVE_PRESET <name>` (runs on next start), `QUEUE_PRESET <name>` (switches at the next cycle
boundary, mid-run). There is deliberately NO remote START yet (StartMacro can raise a blocking MsgBox
with nobody present; add it only after StartMacro reports startup errors through the status/ack channel).

Concurrency model — this touched `StartMacro`, `MainLoop`, the Escape hotkey and the STOP command;
read this before editing any of them. Relevant globals: `PendingPresetSwitch`,
`PresetSwitchRestartPending`, `StopRequested`, `MacroActive`.

- `StartMacro` claims a session by setting `MacroActive := true` and resetting the per-session flags
  ATOMICALLY under `Critical`; the entry guard rejects re-entry on `Running || MacroActive`; a
  `try/finally` guarantees `MacroActive` is released on EVERY exit (so a stuck flag can't block Start).
- A remote `STOP` / Escape latches `StopRequested` and cancels any queued switch. `StartMacro` checks
  `StopRequested` atomically (under `Critical`) right before `Running := true`, so a stop that lands
  during restart prep (including inside `ForceGameWindow`'s `Sleep`) is honored, not overwritten.
- `QUEUE_PRESET` is committed by `MainLoop` at the cycle boundary (sets `PresetSwitchRestartPending`),
  and `StartMacro` restarts into it — reusing the same restart path as disconnect auto-reconnect
  (`DisconnectRestartPending`).
- `MacroActive` also lets the remote STOP ack distinguish "genuinely idle" (reject: "Not running")
  from "mid restart prep, so the stop latch will take effect" (acknowledge: "Stopping").

### Roadmap

- **Phase 1 — Local agent (Go, single `.exe`).** Reads `remote_status.json`, tails `macro_log.txt`,
  atomic-publishes `remote_cmd.txt`, reads `remote_ack.txt`. Device pairing (one-time code exchanged
  for a device token). Outbound long-poll (simpler, preferred first) or WebSocket to the backend.
  Develop against a local test backend before any cloud.
- **Phase 2 — Cloud backend + web MVP (single user / single device).** Accounts + login, device
  pairing, live status view, log view, the whitelisted controls. TLS via Caddy or a Cloudflare Tunnel.
  SQLite is fine at this stage; move to Postgres in Phase 3.
- **Phase 3 — Multi-tenant + hardening.** Every row keyed by `user_id`; per-user device pairing; TOTP
  2FA; rate limiting; audit log; token revocation; agent auto-update + code signing.
- **Phase 4 — Operations.** Monitoring, backups, secret management.

Data-model sketch: `users`, `devices` (user_id, token_hash, revoked_at), `macro_state` (device_id,
state, preset, updated_at), `commands` (device_id, type, payload, status), `logs`, `audit`.

## Codex delegation

Delegate implementation to Codex through the repo wrapper `tools/codex-delegate.mjs` (it runs
`codex exec --json` and surfaces Codex's full reasoning trace, which the `/codex:rescue` plugin
command drops) instead of writing it yourself. Pick the model by how hard the task is:

- Simple / low-reasoning subtasks (bug fixes, boilerplate, simple refactors, writing tests,
  repetitive changes) -> gpt-5.6-luna:

      node tools/codex-delegate.mjs --model gpt-5.6-luna --effort <level> "<concrete, clearly scoped task>"

- Complex logic (non-trivial algorithms, tricky state handling, multi-step refactors) ->
  gpt-5.6-terra. Do NOT implement complex logic yourself anymore -- delegate it to terra:

      node tools/codex-delegate.mjs --model gpt-5.6-terra --effort <level> "<concrete, clearly scoped task>"

You choose `--effort` yourself (none|minimal|low|medium|high|xhigh) to match the task's difficulty --
lower for simple edits, higher for subtle logic.

It runs Codex in the workspace-write sandbox so Codex can implement the change; add `--read-only`
for investigations that must not touch files. The wrapper streams Codex's full reasoning live, line
by line, into a per-model Markdown file in the repo root (`codex-reasoning-<model>.md`, gitignored;
override with `--reasoning-file <path>`). Each file opens its own VS Code tab the moment it receives
its first thought-process update, if not already open (`code -r`, best-effort; per model,
independently; use `--no-open` to skip). New runs APPEND a new dated section — previous thought
processes are kept;
delete the file to clear it. If that file is already held by another running instance, the run
streams to a separate temp file instead (also opened in VS Code), so simultaneous runs never
interleave. The open tab live-updates as reasoning streams (or `tail -f` it).

After a workspace-write delegation the wrapper AUTO-REVIEWS the change: it detects which files the
delegation touched and runs a read-only review of just those files with the reviewer one tier up
(luna -> terra, terra -> sol), streaming that review into the reviewer's own tab. To stdout, and
thus into this chat, it prints the delegation answer plus the auto-review findings (and both
reasoning-file paths). Relay those as-is (do NOT paste the reasoning into the chat), then act on the
findings. Use `--no-review` to skip the auto-review (e.g. to bundle several delegations before one
review) and `--review-effort <level>` to set the review's effort.

Still implement yourself (do NOT delegate): architecture decisions, security-relevant code (auth,
data processing, payments), and anything where a mistake would be especially costly or hard to
reverse.

Delegated subtasks are reviewed automatically by the wrapper (above) at the correct tier. For work
you implemented YOURSELF (architecture / security / anything too risky to delegate), run the review
manually through the wrapper with `--read-only` and gpt-5.6-sol, scoped to ONLY the change you made
(the file(s) from `git status` and their immediate context -- the change, not whole files):

      node tools/codex-delegate.mjs --read-only --model gpt-5.6-sol --effort <level> "Review the CHANGES to <the changed file(s)> and their immediate context. Focus on what you added or modified; do NOT re-report unrelated pre-existing code. Report issues with file:line; if none, say it looks good. Do not modify files."

You choose `--effort` by how subtle the change is. For a broader sweep over ALL uncommitted changes
at once, use gpt-5.6-sol (this is also what the stop-gate runs at turn-end).

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
