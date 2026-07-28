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
  run it ("it's fine right now" / "go ahead and open it") or when it helps your work greatly ask the user if youre allowed to via the askuserquesyion tool. Verify changes by reading the code
  and reasoning about it instead.
- **Work in an isolated git worktree per task.** Multiple Claude/Codex sessions can run against
  this repo at the same time. Before starting a task, work in an isolated worktree instead of the
  shared checkout — `EnterWorktree` in this harness, or `git worktree add <path> -b <branch>` from
  a plain terminal/Codex session — so a concurrent session's branch switches, stashes, resets, or
  commits cannot interfere with your files mid-task. If you ever do find yourself in the shared
  checkout with pre-existing uncommitted changes that are not part of your task, they belong to
  another session's in-progress work: leave them completely untouched (no staging, stashing,
  resetting, or committing) and stage/commit only the exact files your own task changed.

## Project overview

Kimberlite's Anime Expedition Macro — an AutoHotkey v2 GUI automation tool for the Roblox tower-defense
game "Anime Expedition". It drives the game window through a configurable screen state machine:
detecting on-screen states (via OCR), clicking buttons, dragging the camera, placing towers, and
looping rounds automatically.

## Layout

The repository is split into two top-level folders: `macro/` (the application and all its runtime
files) and `remote/` (the optional remote access agent + backend/web UI, which also hosts the user
documentation as a tab — see "Documentation" below). All macro file paths below are relative to
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

## Documentation

There is no more standalone `website/` folder or GitHub Pages deployment for the user guide — it now
lives as the "Documentation" tab of `remote/server/web/index.html` (the remote access site), so the
guide and the remote-control dashboard are one self-contained site instead of two. `index.html` wraps
the existing login/dashboard views (now inside `#app-views`) plus a new `#docs-view` section holding
the full guide, switched via a persistent top nav bar; the tab switch is a small inline `<script>` at
the bottom of the file, deliberately independent of `app.js`'s auth/session state machine (`setView`
in `app.js` is untouched). All new documentation CSS in `style.css` is scoped under `.docs-view` so it
cannot leak onto the dashboard's own generic elements (`<p>`, `<code>`, `<table>`, ...); the shared
color/font tokens in `:root` were retuned to the guide's former purple/Inter look so both halves of
the site match. Update the docs content directly in that file's `#docs-view` section — there is no
separate source file or build step for it.

Because the Documentation tab is meant to work by opening `index.html` straight from disk (no backend
running), its asset references must stay `file://`-safe: `style.css`/`app.js` are loaded via
relative, not root-absolute (`/style.css`), paths, and `app.js` is a plain `<script>`, not
`type="module"` (Chromium refuses to load module scripts at all under `file://`, even same-folder
ones) — `app.js` has no `import`/`export`, so this cost nothing. Do not reintroduce either pattern.

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

**Implementation status (all phases below are now implemented under `remote/`).** The agent lives in
`remote/agent/` (Go, stdlib-only single `.exe`) and the backend + web UI in `remote/server/`
(Node + Fastify + Drizzle + better-auth). The wire contract is `remote/PROTOCOL.md`; build/run and
production deployment are `remote/README.md` and `remote/DEPLOY.md`. Stack note: the backend uses the
PostgreSQL dialect throughout via Drizzle — PGlite (pure-WASM, no native build) in dev and
node-postgres in prod — because `better-sqlite3` cannot compile on the current Node/toolchain; this
also pre-satisfies the Phase 3 "move to Postgres". The only remaining work is operator-dependent:
cloud deployment (domain + TLS) and, for fully automated agent self-update, a code-signing certificate.

Pairing no longer requires a terminal, and no longer uses a one-time code: the macro's GUI has its
own "Remote Agent Setup..." window (bottom strip, next to "Enable remote bridge") where the user
enters the agent path/server URL once, then signs in (or registers a brand new account) with that
account's own email/password (plus a TOTP code if 2FA is enabled) and clicks "Pair" - see
`tower_defense_macro_gui.ahk`'s "REMOTE AGENT SETUP WINDOW" section. This still adds NO
networking/JSON parsing to the macro itself: the GUI just launches the same
`animeexpedition-agent.exe --login`/`--register` a user would otherwise run by hand (via `RunWait`,
every dynamic value passed through the `WinArgQuote` CreateProcess-argv-quoting helper so nothing
typed into the email/URL/path fields can inject an extra argument; the password and TOTP code are
passed through a small temp `--credentials-file` instead of the command line, since unlike a
short-lived pairing code a password is sensitive for the account's whole lifetime) and reads the
outcome back from a `--auth-result-file` the agent writes itself (`remote/agent/main.go`). The
backend resolves the credentials directly against better-auth's server API
(`remote/server/src/services/agentAuth.ts`) and creates the device in the same request - there is no
separate pairing-code table or endpoint anymore. "Start Agent"/"Stop Agent" in the same window
control the background agent afterward (detected by process name, not a remembered PID, so status
stays correct across a macro restart).

- **Phase 1 (DONE) — Local agent (Go, single `.exe`).** Reads `remote_status.json`, tails `macro_log.txt`,
  atomic-publishes `remote_cmd.txt`, reads `remote_ack.txt`. Device pairing (the account's own
  credentials exchanged for a device token) — from a terminal, or from the macro's own GUI (see
  above). Outbound long-poll (simpler, preferred first) or WebSocket to the backend. Develop against a
  local test backend before any cloud.
- **Phase 2 (DONE) — Cloud backend + web MVP (single user / single device).** Accounts + login, device
  pairing, live status view, log view, the whitelisted controls. TLS via Caddy or a Cloudflare Tunnel.
  SQLite is fine at this stage; move to Postgres in Phase 3.
- **Phase 3 (DONE, except code-signed self-update) — Multi-tenant + hardening.** Every row keyed by
  `user_id`; per-user device pairing; TOTP 2FA; rate limiting; audit log; token revocation; agent
  version/update-check (self-update needs a code-signing certificate — operator-provided).
- **Phase 4 (DONE) — Operations.** `/health` + `/health/ready`, DB backups (`scripts/backup.mjs`),
  env-based secret management, deploy guide (`DEPLOY.md`).

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
findings) in the chat; its reasoning streams to the reasoning file, not the chat. The
`model_reasoning_summary` / `show_raw_agent_reasoning` settings in `~/.codex/config.toml` control
whether Codex produces a human-readable thought process at all; they are currently commented out
(disabled, to save tokens) since no one needs to read the reasoning file right now — re-enable them
there if that changes.

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
