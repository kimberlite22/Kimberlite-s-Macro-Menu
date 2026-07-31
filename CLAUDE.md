# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Hard rules (always follow)

- **Everything in English.** All code, comments, GUI text, tooltips, log messages, and documentation,
  even when the user chats in another language.
- **No emojis.** Never in anything that reaches the application (code, GUI text, tooltips, log
  messages) or in how Codex output and reasoning are presented (headings, section labels, findings).
  Plain text labels only. This holds even when the user chats with emojis.
- **No em dashes.** Never in anything you write: code, comments, GUI text, tooltips, log messages,
  documentation, commit messages, or chat replies. Use a period, comma, colon, semicolon, or
  parentheses instead, whichever reads most naturally. If text you are editing already contains one,
  replace it rather than adding more.
- **Do NOT open / run the AHK application while testing.** Never launch
  `tower_defense_macro_gui.ahk` (or otherwise start the macro on screen) to verify changes. Verify by
  reading the code and reasoning about it. Only exception: the user explicitly says it is OK right
  now, or you ask for permission first via the AskUserQuestion tool because running it would help
  your work greatly.
- **`tasklist/` is the backlog.** When the user mentions "a task" / "the next task" without
  describing it, its description is one of the files under `tasklist/open/`;
  `tasklist/OVERVIEW.md` is the fastest way to find which one. Read that first instead of asking
  what the task is, and follow the "Tasklist routine" below whenever you touch anything in
  `tasklist/`.
- **Work in an isolated git worktree per task.** Multiple Claude/Codex sessions can run against this
  repo at the same time, so work in a worktree instead of the shared checkout (`EnterWorktree` in
  this harness, or `git worktree add <path> -b <branch>` elsewhere) so another session's branch
  switches, stashes, resets, or commits cannot interfere mid-task. If you do find yourself in the
  shared checkout with pre-existing uncommitted changes that are not part of your task, they belong
  to another session: leave them completely untouched (no staging, stashing, resetting, committing)
  and stage/commit only the exact files your own task changed. After completing a task, commit in the
  worktree, push the branch, open a pull request into main, merge it (`gh pr merge <branch> --merge`)
  and then delete the remote branch with `git push origin --delete <branch>`, so the remote branch
  list stays a truthful list of what is actively being worked on (see "Claiming a task"). Merge it
  right away, without stopping to ask for confirmation first: this holds even when a harness's own
  default is to open a draft PR and stop there (for example, a background-job convention of "commit,
  push, open a draft PR, do not merge"). That default exists for repos in general; this repo's own
  instruction here is more specific and wins for work done in this repo, so open the PR as a normal
  (non-draft) PR and merge it in the same run. Do NOT use
  `gh pr merge --delete-branch` from inside a worktree: it merges, then tries to check out main for
  the local cleanup, and dies with "'main' is already used by worktree at ..." because the shared
  checkout holds main. The PR ends up merged with the branch still there, which is the one state
  this rule is trying to avoid. `gh` is installed and authenticated; if it is not on PATH it lives
  at `C:\Program Files\GitHub CLI\gh.exe`, and a multi-line PR body has to go through `--body-file`,
  since Windows argv quoting mangles `--body`.
  Then remove the worktree itself (`ExitWorktree` with `action: "remove"` in this harness, or
  `git worktree remove <path>` elsewhere after leaving its directory) so it does not linger as dead
  weight once the branch behind it is gone. If removal fails because a file inside it is locked, do
  not just leave the worktree behind: find what still holds the file open (on Windows,
  `Get-CimInstance Win32_Process | Where-Object { $_.Path -like "*<worktree-path>*" }`) and stop it,
  then retry. A `gui.exe` left running from a local, manually reproduced release build is one way
  this happens: `release.yml`'s own smoke-test step does stop it (`Stop-Process` after the check), so
  this is specifically a risk of interrupting a local run of those same steps outside CI, not a bug
  in the workflow.
  Do this for every task unless the user explicitly says otherwise. This rule WINS over a
  session-level default that says to work in place or to skip `EnterWorktree`; only the user saying
  so in the current conversation overrides it. If the worktree later blocks you from editing a file
  outside the repo copy (for example `.claude/settings.local.json`), finish and merge the branch
  first, then leave the worktree and do the rest from the shared checkout.
- **Whatever you set up has to work for every Claude account in this directory.** Several accounts
  work in this same checkout, and each one has its own profile: its own memory directory, its own
  chat history, its own `.claude/settings.local.json` view. So anything the next session needs
  belongs in the repo, where it is committed and shared: `CLAUDE.md` for rules, project skills in
  `.claude/skills/`, helper scripts in `tools/`, the backlog in `tasklist/`. Account-local memory
  is fine as a personal shortcut, never as the only copy of a fact someone else needs. Committed
  files must not contain user-specific paths (`C:\Users\<name>\...`) or assume one account's setup;
  a machine-level path belongs in the text only as a named fallback, the way the `gh` path above is
  written. When a task ends with "I saved that to memory", ask yourself whether it also needs a line
  in this file.
- **Report workflow obstacles at the end of every task.** See "Workflow feedback" below.

## Workflow feedback (end of every task)

End each task with a short **Workflow feedback** section listing anything that got in your way and
that the user could fix, so the next task is faster, simpler, and cheaper in tokens. What belongs
there:

- Missing or stale local prerequisites that forced extra steps or blocked verification (an unbuilt
  `macro/ocr_server.exe`, a missing `remote/agent/animeexpedition-agent.exe`, missing tooling).
- Permission prompts or sandbox denials that interrupted an otherwise routine command, together with
  the allowlist entry that would prevent them next time.
- Information that was missing, outdated, or wrong in this file or the other docs and that cost you
  exploration to rediscover.
- Questions you had to ask the user that a one-line note in this file would have answered.
- Manual steps the user had to perform that could be scripted, and repeated large file reads that a
  helper script or a narrower file layout would avoid.

Keep it to concrete items, each with the concrete fix. Omit the section entirely when nothing is
worth reporting; do not pad it with generic advice.

## Tasklist routine (`tasklist/`)

`tasklist/` in the repo root is the backlog of everything the user still wants done, and the place to
look up what a task actually means: one file per task, so two sessions working on different tasks
never touch the same file. It is tracked in git like any other file: edit it in your worktree and
commit the tasklist change together with the work it describes, in the same PR.

The `tasklist` skill (`.claude/skills/tasklist/SKILL.md`) is the trigger for this routine. It is
deliberately thin and points back here, so the rules live in exactly one place: when you change the
layout below, check whether the skill's trigger description still matches.

**Layout** (fixed, do not invent new top-level groups):

    tasklist/INBOX.md              raw one-liners the user jots down, unsorted, often German
    tasklist/open/fixes/*.md       broken behavior, highest priority group
    tasklist/open/workflow/*.md    tooling, delegation, docs, repo hygiene
    tasklist/open/gui-ux/*.md      presentation and usability
    tasklist/open/major/*.md       architecture / logic changes and new subsystems
    tasklist/done/*.md             finished tasks
    tasklist/OVERVIEW.md           generated summary, see "Regenerating OVERVIEW.md"
    tasklist/PENDING_REVIEW.md     hand-maintained, see "Pending release lists"
    tasklist/PENDING_RELEASE.md    hand-maintained, see "Pending release lists"

A task file's name is a short slug (`pin-rename.md`), never a number: reprioritizing only ever edits
a `Prio:` field, it never renames a file.

**Task file format**, nothing more than these fields:

    Title: <the user's own wording, kept verbatim, can be several lines>
    Prio:  <integer, lower = sooner, unique within its group>

    Goal:  what is true once this is done, in one or two sentences
    Files: the concrete files / functions / GUI windows the change touches
    Steps: the numbered implementation steps, small enough to act on directly
    Open:  decisions you cannot make alone, or "-" when there are none

Keep `Title` verbatim even when German or telegraphic: it is the user's note, not documentation.
Everything else you write is English, like the rest of the repo.

**Just-in-time planning.** When a new task is created from `INBOX.md`, only the file that becomes the
lowest `Prio` in its group gets full `Files:`/`Steps:` right away; every other new file stops after
`Goal:` and `Open:`. Reason: detailed planning for a task that will not start soon tends to go stale
before its turn comes, since the code underneath it keeps moving, so the effort is better spent right
before the task actually starts, as part of the branch that does the work. This is a rule about NOT
front-loading planning effort for later, not a mandate to strip `Files:`/`Steps:` out of a file that
already has them: a plan that is still accurate is not made better by deleting it. When a task
becomes the new lowest `Prio` in its group and its file still only has `Goal:`/`Open:`, add the
missing `Files:`/`Steps:` at that point, re-checking them against the current code either way.

**Routine.** Run it whenever the user asks to sort/update the backlog, when they add something to
`INBOX.md`, and as the first step of any task taken from here:

1. Read `INBOX.md`. For every line that is complete enough to act on: pick its group, create
   `tasklist/open/<group>/<slug>.md`, fill in `Title` (verbatim) and `Goal`, then remove the line
   from INBOX. A half-finished line stays in INBOX untouched; ask about it instead of finishing the
   sentence for the user. Only the new lowest-`Prio` file per group gets full `Files:`/`Steps:` right
   away (see "Just-in-time planning"); the rest stay at `Goal:`/`Open:`.
   Assign its `Prio` by actually judging it against the group's other open tasks (impact against
   effort, whether it blocks or is blocked by something else in the group), renumbering existing
   entries if it slots in ahead of them; state the reasoning in the chat so the user can override it.
   Appending it as the group's lowest priority is the fallback for when there is no real basis to
   judge yet, not the default.
2. Never invent a task, never silently drop or reword one, and never delete a task file outright,
   move it to `tasklist/done/` instead (step 5).
3. Do not change `Prio` values or re-plan a file that already has one unless the priority genuinely
   changed. When you do reorder, say so in the chat with the reason.
4. Before planning a task file in detail, check whether it is already implemented. Files can sit
   untouched while the code moves on; if it is done, skip straight to step 5 with the evidence
   instead of planning work that no longer exists.
5. When a task is finished: `git mv` its file from `tasklist/open/<group>/` to `tasklist/done/`, and
   replace its body with:

       Title:     <verbatim, unchanged>
       Completed: <date>
       Commit:    <hash, or "-" when there is none>

       Result: <one-line result>

   Drop `Prio:`, it no longer means anything once a task is done. Also append a line for it to
   `tasklist/PENDING_REVIEW.md` (see "Pending release lists"), since finishing a task here means a
   Claude session just made the change, not that the user has tried it yet.
6. Regenerate `tasklist/OVERVIEW.md` (below) whenever `open/` or `done/` changed.

**Regenerating OVERVIEW.md.** It is derived, never hand-edit it and never manually reconcile a merge
conflict in it: list every group in the fixed order above, inside each group the files sorted by
`Prio`, each line a link plus the `Goal:` in a few words, then a "DONE (newest first)" section built
from the `Completed:` dates. On a conflict, regenerate it from the current `open/`/`done/` files and
overwrite both sides; there is nothing in it worth reconciling by hand.

**Pending release lists (`tasklist/PENDING_REVIEW.md`, `tasklist/PENDING_RELEASE.md`).** Two
hand-maintained files that stage a finished change through two rounds of the user's own testing
before it ships, on top of (not instead of) the normal `tasklist/done/` record, which already holds
the permanent history the moment a task's PR merges:

    tasklist/PENDING_REVIEW.md     changes a Claude session just made; the user has not tried them
    tasklist/PENDING_RELEASE.md    changes the user already approved once; one more check before a
                                    release ships them

Unlike `OVERVIEW.md`, neither file is ever regenerated: both accumulate and empty by hand, because
"the user just approved this" and "the user just cut a release" are one-off decisions no source file
encodes.

Each `tasklist/PENDING_REVIEW.md` entry is two lines, the second one deliberately left for the user
to fill in directly in the file, no chat needed:

    - <slug> - <one-liner>
      Review:

- **Finish a task -> `PENDING_REVIEW.md`.** The moment a task's file moves to `tasklist/done/` (step
  5 above), append both lines above (an empty `Review:`) to `tasklist/PENDING_REVIEW.md`, grouped by
  the task's own group in the same fixed order as `OVERVIEW.md` (fixes, workflow, gui-ux, major),
  creating the group heading if this is that group's first pending entry.
- **The user fills in `Review:`.** Whether it counts as an approval is a strict, whole-line match
  (trimmed, case-insensitive) against a fixed approval list: `approved`, `ok`, `okay`, `yes`, `lgtm`.
  Anything that is not an exact match on that list, including an approval word plus extra text
  (`approved, but crashes on second run` is NOT an approval), is read as a follow-up
  change to make in full, the user's own words in whatever language, no particular format required,
  e.g. "button still too small" or "crashes on the second run".
- **The tasklist skill resolves filled-in entries first, every time it runs**, before doing whatever
  else was asked (see the tasklist skill for where this sweep sits): for every
  `tasklist/PENDING_REVIEW.md` entry whose `Review:` line is non-empty,
  - an exact approval word moves the entry (drop the now-served `Review:` line) to the matching group
    in `tasklist/PENDING_RELEASE.md`, as `- [ ] <slug> - <one-liner>`;
  - anything else turns into a new task file under `tasklist/open/<group>/`, the same way an
    `INBOX.md` line becomes one, with two differences: `Title` is the `Review:` text copied verbatim
    (whatever language it is in, like an `INBOX.md` line), and `Goal` is an English sentence written
    from it that also names where it came from, e.g. "Follow-up from `<slug>`: the button is still
    too small." (same group as the original task by default, `Prio` judged against the group's other
    open tasks). The `PENDING_REVIEW.md` entry is then dropped entirely, since the follow-up is now
    tracked, with its provenance, as its own task instead.
  - regenerate `tasklist/OVERVIEW.md` afterward if any new task file was created this way.
- **Cut a release -> final check, then clear.** Before publishing a release, retest every still
  unchecked entry in `tasklist/PENDING_RELEASE.md` one more time, checking it off as `- [x]` once
  confirmed. Once every entry is checked, clear the file down to its own explanatory header (the
  hand-written intro text and the `- [ ] <slug> - <one-liner>` template line stay; every actual
  pending entry and now-empty group heading is removed). Nothing moves out of `tasklist/done/`: that
  record is permanent and unrelated to either file's own lifecycle.
- Neither file ever holds anything besides tasks that just finished, or that were just resolved
  through their own `Review:` line: no manually added entries, no re-flagging an already-shipped line
  after the fact through any other channel. If a shipped change turns out to be broken later, after
  its `PENDING_RELEASE.md` entry was already cleared, that is a new bug, tracked the normal way as a
  new file under `tasklist/open/fixes/`.

**Claiming a task.** Before starting a task, check whether another session is already on it:

    git ls-remote --heads origin              # every branch in flight, one per task
    gh pr list --state all --head <branch>    # whether that exact branch already had a PR

`--head` keeps the PR check deterministic; a bare `gh pr list` shows only open PRs and caps its
output, so it can quietly miss one.

Name the worktree after the task so the branch name says what is claimed (`EnterWorktree` turns
`pin-rename` into the branch `worktree-pin-rename`), and push it immediately after creating it,
before writing any code: `git push -u origin <branch>` publishes the branch even with no commits on
it yet. That push is the claim, it costs one command, and it is visible to every account and machine
at once. If the task is already claimed, take the next one down instead and say in the chat which
one you skipped and why.

Know what this buys and what it does not. It catches the realistic case: a second job dispatched
minutes or hours after the first. It is NOT a lock. Two sessions that check and push within the same
few seconds both succeed, because pushing a branch that already points at the same commit is a no-op
rather than an error, so the loser never learns it lost. Nothing here serializes them.

The other half is keeping the registry truthful, and that part is manual: after merging, delete the
branch with `git push origin --delete <branch>` (not `gh pr merge --delete-branch`, see the worktree
rule) and check that it is really gone, since a crash, an abandoned PR or a failed deletion all
leave one behind. A branch that is already merged into main, or that has no commits and no open PR,
is leftover from a dead session rather than an active claim. Say so and let the user clean it up; do
not silently take the task over, and do not treat the stale branch as proof that somebody is working
on it.

Deliberately NOT an "in progress" marker inside a task file: it would only reach other sessions after
a merge to main, so it could not be set before starting work anyway, and a crashed session would
leave it set with nobody to clear it. A branch is still the better flag: it lives outside the files
everyone edits, and merging the PR clears it.

**Session title.** As soon as a task is identified (claimed, or answering "what is next"), set the
terminal window/tab title to `[<group>][P<prio>] <slug>`, for example `[gui-ux][P2]
map-placement-box-size`, so several open sessions working different tasks stay distinguishable at a
glance. The slug is already a short English identifier, it doubles as the one-line description; no
need to also cram in the `Goal:` text. Use whichever of these matches the shell actually running the
command: PowerShell, `$host.UI.RawUI.WindowTitle = "[gui-ux][P2] map-placement-box-size"`; Bash, the
ANSI OSC 0 sequence, `printf '\033]0;%s\007' "[gui-ux][P2] map-placement-box-size"`. This only reaches
the terminal emulator's own window/tab title; it cannot rename the session's entry in a job list or
sidebar the harness draws, there is no tool for that.

**Parallel sessions.** One file per task already removes most of the shared-file risk: two sessions
working on different tasks never touch the same file, so most PRs under `tasklist/` cannot conflict
with each other at all. What is still shared ground:

- `tasklist/INBOX.md` and `tasklist/OVERVIEW.md`. Commit changes to them as their own commit,
  separate from the code commits, and rebase onto the latest main before merging: `git fetch origin`
  then `git rebase origin/main` in the worktree. Not a bare `git pull --rebase`, which rebases onto
  the branch's own upstream (your pushed feature branch), not onto main.
- A conflict in `INBOX.md` is a set of lines: keep every line from both sides, in any order.
- A conflict in `OVERVIEW.md` is never worth resolving by hand: throw both sides away and regenerate
  it from `open/`/`done/` instead.
- Two sessions racing the branch-claim check within the same few seconds (see "Claiming a task") can
  still both end up editing the SAME task file. That is still a real conflict, but now it is confined
  to that one task's own file instead of dragging in somebody else's unrelated entry the way a shared
  list did.

## Project overview

Kimberlite's Anime Expedition Macro: an automation tool for the Roblox tower-defense game "Anime
Expedition", a PySide6 window in front of an AutoHotkey v2 engine. It drives the game window through
a configurable screen state machine: detecting on-screen states (via OCR), clicking buttons, dragging the camera, placing towers,
and looping rounds automatically.

## Layout

Four top-level folders: `macro/` (the AHK engine and all its runtime files), `gui/` (the PySide6
presentation process, built into the single executable the release ships), `ocr/` (the OCR helper's
Python source, built into `macro/ocr_server.exe`), and `remote/` (the optional remote access agent
plus backend/web UI, which also hosts the user documentation as a tab). All macro paths below are
relative to `macro/`; the app resolves them via `A_ScriptDir`, so everything it reads/writes
lives next to `tower_defense_macro_gui.ahk`.

- `macro/tower_defense_macro_gui.ahk`: the whole application (~7000 lines, AutoHotkey v2). GUI, state
  machine, input, OCR client, config load/save.
- `macro/config.ini`: all settings, presets, screens and steps. **UTF-16LE**, gitignored (user-local).
- `macro/config_backups/`: timestamped automatic backups of `config.ini`.
- `macro/ocr_server.exe`: OCR helper, built from `ocr/` via PyInstaller (see `ocr/BUILD.md`).
  Gitignored build artifact; a dev/source checkout must build it once.
- `macro/macro_log.txt`, `macro/ocr_result*.txt`: runtime log / OCR output files.
- `macro/remote_bridge.ahk`: optional local remote bridge, `#Include`d at the end of
  `tower_defense_macro_gui.ahk`. Off by default.
- `macro/remote_status.json` / `macro/remote_cmd.txt` / `macro/remote_ack.txt` (+ `.tmp`): runtime
  files for the remote bridge; gitignored, regenerated at runtime.

## Key conventions (read before editing)

- **Coordinates are stored as percent-of-opening**, not raw screen pixels. The game window is pinned
  into a fixed "opening" rectangle (General / Game Window tab); every click and detection corner is a
  percentage (0-100) of that opening so presets survive moving/resizing/monitor changes. The
  opening's own geometry (`HoleX/Y/W/H`) stays in absolute pixels; it is the reference frame. Convert
  with `PctXFromAbs` / `PctYFromAbs` (store) and `AbsXY` (read).
- **One-time config migration.** `MigrateCoordsToPercent()` converts legacy absolute-pixel configs to
  percent once, then stamps `[General] CoordFormat=percent`. It is type-aware (e.g. a "Zoom Out" step
  keeps a wheel-tick count in X and must not be converted). Runs before any value is read.
- **`SendMode "Event"`** is deliberate: the game ignores the default SendInput mode. Do not change
  it. ("Play" mode failed to move the cursor at all on the target system.)
- **Lenient numeric parsing.** Use `SafeInt` / `SafeNum` for user-entered numbers; they trim
  whitespace and accept a comma as a decimal separator (German locale) instead of crashing.

## GUI tabs & hotkeys

- Tabs: **Preset Settings**, **Map Placement**, **General**.
- Hotkeys: `F7` pin the game window, `F8` capture position at cursor, `F9` pause/resume, `F10` start
  macro, `Escape` emergency stop / cancel capture.

## Documentation

There is no standalone `website/` folder or GitHub Pages deployment. The user guide lives as the
"Documentation" tab of `remote/server/web/index.html` (the remote access site): the login/dashboard
views sit inside `#app-views`, the guide inside `#docs-view`, switched by a small inline `<script>`
at the bottom of the file that is deliberately independent of `app.js`'s auth/session state machine
(`setView` in `app.js` is untouched). Edit the guide directly in that `#docs-view` section; there is
no separate source file or build step.

Two constraints that must not be regressed:

- All documentation CSS in `style.css` is scoped under `.docs-view` so it cannot leak onto the
  dashboard's generic elements (`<p>`, `<code>`, `<table>`, ...).
- The tab must work when `index.html` is opened straight from disk with no backend, so asset
  references stay `file://`-safe: `style.css`/`app.js` are loaded via relative (not root-absolute)
  paths, and `app.js` is a plain `<script>`, not `type="module"` (Chromium refuses module scripts
  under `file://`, even same-folder ones). `app.js` has no `import`/`export`, so classic-script
  loading costs nothing; keep it that way. Do not reintroduce either pattern.

## Remote access (implemented)

A website with user accounts that gives remote access to the macro: live status, logs, and a small
set of safe controls. Three layers:

    [Browser / phone] --HTTPS--> [Cloud backend + website] <--outbound-- [Local agent] <--files--> [AHK macro]
       (user login)              (accounts, API, DB)         (only net I/O)  (Go, single .exe)   (this repo)

The home PC only ever makes OUTBOUND connections, so no port forwarding. The AHK macro does NO
networking: it only reads/writes local files, exactly like the OCR helper. Code lives in
`remote/agent/` (Go, stdlib-only single `.exe`) and `remote/server/` (Node + Fastify + Drizzle +
better-auth, PostgreSQL dialect throughout: PGlite in dev, node-postgres in prod). Wire contract:
`remote/PROTOCOL.md`. Build/run and deployment: `remote/README.md`, `remote/DEPLOY.md`. The only
remaining work is operator-dependent: cloud deployment (domain + TLS) and a code-signing certificate
for automated agent self-update.

### Security model (non-negotiable)

- The command channel is UNTRUSTED input. It may ONLY trigger a fixed whitelist of predefined
  actions: never raw coordinates, keystrokes, scripts, or arbitrary preset data. Validate every field
  against existing state before acting (e.g. a preset name must already exist).
- Outbound-only from the home PC; device-specific, revocable pairing tokens (separate from the user
  login); TLS everywhere; rate limiting plus an audit log of remote actions. Do NOT hand-roll auth or
  crypto.

### Local bridge protocol (`macro/remote_bridge.ahk`)

Off by default via the "Enable remote bridge" checkbox (General tab, bottom strip), persisted to
`[General] RemoteBridgeEnabled`; the checkbox is the live source of truth (read each tick, like
`disconnectEnabledChk`). File protocol in `A_ScriptDir`, mirroring the OCR helper (atomic `.tmp` +
`FileMove`, a request token, consume-on-read):

- `remote_status.json`: macro writes ~1x/sec; the `timestamp` field doubles as a heartbeat (stale =
  offline). Run state, active/running/queued preset, current map/screen/step, counters.
- `remote_cmd.txt`: the agent writes one command `<token>|<TYPE>|<arg>`; the macro consumes (deletes)
  it on read, so each command runs at most once.
- `remote_ack.txt`: macro writes `<token>|<ok|error>|<message>`.
- Logs are NOT duplicated into status; the agent tails `macro_log.txt` directly.

Command whitelist, each mapping onto the SAME mechanism a local hotkey/button uses, so a remote
command can never do more than a local key press: `PAUSE`, `RESUME`, `STOP`,
`SET_ACTIVE_PRESET <name>` (runs on next start), `QUEUE_PRESET <name>` (switches at the next cycle
boundary, mid-run). There is deliberately NO remote START: `StartMacro` can raise a blocking MsgBox
with nobody present; add it only after StartMacro reports startup errors through the status/ack
channel.

### Concurrency model (read before editing StartMacro, MainLoop, the Escape hotkey, or STOP)

Relevant globals: `PendingPresetSwitch`, `PresetSwitchRestartPending`, `StopRequested`, `MacroActive`.

- `StartMacro` claims a session by setting `MacroActive := true` and resetting the per-session flags
  ATOMICALLY under `Critical`; the entry guard rejects re-entry on `Running || MacroActive`; a
  `try/finally` guarantees `MacroActive` is released on EVERY exit, so a stuck flag cannot block
  Start.
- A remote `STOP` / Escape latches `StopRequested` and cancels any queued switch. `StartMacro` checks
  `StopRequested` atomically (under `Critical`) right before `Running := true`, so a stop landing
  during restart prep (including inside `ForceGameWindow`'s `Sleep`) is honored, not overwritten.
- `QUEUE_PRESET` is committed by `MainLoop` at the cycle boundary (sets
  `PresetSwitchRestartPending`), and `StartMacro` restarts into it, reusing the same restart path as
  disconnect auto-reconnect (`DisconnectRestartPending`).
- `MacroActive` also lets the remote STOP ack distinguish "genuinely idle" (reject: "Not running")
  from "mid restart prep, so the stop latch will take effect" (acknowledge: "Stopping").

### Pairing and agent bundling

Pairing needs no terminal and no one-time code. The macro's GUI has a "Remote Agent Setup..." window
(bottom strip, next to "Enable remote bridge"; see the "REMOTE AGENT SETUP WINDOW" section in
`tower_defense_macro_gui.ahk`) where the user enters the agent path and server URL once, then signs
in or registers with that account's own email/password (plus TOTP if enabled) and clicks "Pair".
"Start Agent"/"Stop Agent" in the same window control the background agent afterward (detected by
process name, not a remembered PID, so status survives a macro restart).

This adds NO networking or JSON parsing to the macro. The GUI just launches
`animeexpedition-agent.exe --login`/`--register` via `RunWait` and reads the outcome from the
`--auth-result-file` the agent writes (`remote/agent/main.go`). Security details that must not be
regressed: every dynamic value goes through the `WinArgQuote` CreateProcess-argv-quoting helper so
nothing typed into the email/URL/path fields can inject an argument, and the password and TOTP code
are passed through a small temp `--credentials-file` instead of the command line. The backend
resolves credentials against better-auth's server API (`remote/server/src/services/agentAuth.ts`) and
creates the device in the same request.

The agent ships bundled inside the default release build: `.github/workflows/release.yml` runs
`go build` before compiling the AHK app, and `EnsureBundledRuntimeFiles()`/`FileInstall` extracts it
next to the installed app on every startup, like the OCR helper. It is optional (a failed extraction
does not abort startup, unlike the OCR helper, since the bridge is off by default), and
`DefaultRemoteAgentPath()` checks the bundled copy before the dev/source `remote/agent/` sibling
path. A source checkout still needs its own `go build -o animeexpedition-agent.exe .` in
`remote/agent/` (see `remote/README.md`).

## Python migration initiative

Decided three-way split of `macro/tower_defense_macro_gui.ahk`, chosen because the user is fluent in
Python but not AutoHotkey, wants a genuinely nicer-looking GUI, and wants room to grow the
image-recognition side.

- **Engine (input simulation + state machine / main loop) stays AHK.** `ActClick`/`ActSend`/
  `DragRightClick`, `SendMode "Event"`, `StartMacro`/`MainLoop`/`RunSteps`, and the fullscreen
  overlay/window-lock are reliable and would be the highest-risk rewrite: `SendMode "Event"` is
  empirically required (see "Key conventions") because the game silently ignores `SendInput`, and the
  common Python input libraries (`pyautogui`, `pydirectinput`) use `SendInput` internally. A rewrite
  would mean raw `mouse_event`/`keybd_event` via `ctypes` for no gain.
- **Perception (OCR) moved to Python. DONE, see below.**
- **Presentation (the GUI) moved to Python (PySide6/Qt). DONE, see below.** PySide6 was chosen over
  CustomTkinter/Tkinter because the app needs non-trivial widgets (drag-to-reorder step list, tabs,
  several secondary windows, a capture-mode crosshair overlay) and QSS gives CSS-like styling in
  pure Python.

### Python GUI (`gui/` -> `gui.exe`): DONE

PyInstaller builds `gui/dist/gui.exe`; the release publishes that same binary under the branded name
`Kimberlites-Anime-Expedition-Macro.exe`, deliberately the filename the old AHK auto-updater already
downloads, and it is the only asset the release ships (see "Finalize the single installer exe" in
`.github/workflows/release.yml`). Launched with no arguments it installs itself into
`%LOCALAPPDATA%\Programs\<AppName>`, creates the Start Menu shortcut, extracts the AHK engine
embedded in its own bundle (`dist/AEMEngine.exe`, added via `--add-data`) and launches that engine
hidden, so the user only ever sees the Qt window (`gui/BUILD.md`, `gui/app/self_install.py`,
`gui/app/engine_process.py`, `gui/app/launcher_paths.py`).

    gui/
      app/     main.py, main_window.py, the secondary windows (edit_preset_window.py,
               map_advanced_window.py, option_availability_window.py,
               advanced_outcomes_window.py, remote_agent_window.py), capture.py, widgets.py,
               engine_process.py, launcher_paths.py, self_install.py, update_check.py
      ipc/     client.py, protocol.py, config_reader.py: the local bridge client. protocol.py owns
               the wire types so call sites never hand-assemble dicts.
      tests/   pytest, one module per window plus the IPC layer
      BUILD.md, pyproject.toml

The engine side is `macro/local_bridge.ahk`, `#Include`d like `remote_bridge.ahk` and deliberately
reusing its `RemoteBridgeJsonStr()` / `RemoteBridgeAtomicWrite()` helpers: `#Include` merges both
files into one global namespace, so duplicating a helper there is a redefinition error. Unlike the
remote bridge it is always on, and the channel is local-only, so it does not need the remote
channel's untrusted-input hardening. Runtime files (gitignored, regenerated, same atomic `.tmp` +
`FileMove` shape as the other bridges): `local_status.json`, `local_cmd.txt`, `local_ack.txt`,
`local_capture_result.txt`, `engine_ready.txt`.

AHK still owns `config.ini`, the input simulation and the state machine. The AHK `Gui` code is still
in `tower_defense_macro_gui.ahk`, but the shipped app never shows it: the engine runs hidden behind
the Qt window.

### OCR helper (`ocr/` -> `macro/ocr_server.exe`): DONE

Shipped as a pure 1:1 replacement of the old `ocr_server.ps1`/`ocr_region.ps1` PowerShell helpers
(both deleted): same WinRT `Windows.Media.Ocr` engine via the `winsdk` projection, identical file
protocol, same upscale heuristic, so accuracy is unchanged by construction. `winsdk` was chosen over
`pytesseract`/`EasyOCR`/`PaddleOCR` precisely because it calls the same engine, needs no bundled
model files, and keeps startup fast. `ocr/pyproject.toml` pins `winsdk>=1.0.0b1`, not `>=1.0.0`,
because winsdk has no stable release on PyPI yet.

    ocr/
      ocr_helper/
        engine.py     # OcrEngine: winsdk OCR wrapper + mss capture + Pillow upscale. Builds the
                      # SoftwareBitmap directly from the captured BGRA buffer, no temp PNG.
        protocol.py   # ready/req/resp/stop file protocol, atomic write via .tmp + os.replace.
        cli.py        # --dir alone = server mode; --dir plus --x/--y/--width/--height = one-shot.
      tests/          # test_engine.py asserts the Python engine reproduces a frozen baseline of the
                      # old PowerShell/WinRT output exactly (fixtures/baseline_manifest.json),
                      # including the old engine's own misreads. test_protocol.py covers the files.
      pyproject.toml  # winsdk, mss, Pillow; dev extra: pytest, pyinstaller
      BUILD.md        # PyInstaller build instructions

The AHK-side OCR client (`RunOcrOnRegion` / `EnsureOcrServer` / `RunOcrOneShot` / `StopOcrServer`,
~150 lines) is a self-contained block and the best entry point for understanding the codebase without
reading the rest of the file. Everything downstream (`DetectMapProfileInRegion`,
`IsTextDetectedInRegion`, `TextContainsPartialMatch`, the `RunSteps` detection cases,
`CheckDisconnectTick`, the "Test OCR" buttons) depends only on the protocol below.

**Protocol (do not change; the AHK side depends on it byte-for-byte):**

- Request (`ocr_req.txt`, atomic via `.tmp` + rename): `"<token>|<x>|<y>|<w>|<h>"`.
- Response (`ocr_resp.txt`, same atomicity): `"<token>|<recognized text>"`; AHK discards a response
  whose token does not match its last request.
- `ocr_ready.txt`: written once after the engine initializes; AHK waits up to 15s.
- `ocr_stop.txt`: AHK writes it to request a clean exit; waits up to 600ms before force-killing.
- AHK's own request-response timeout: 6s, then it falls back to the one-shot path.
- Upscale heuristic (keep byte-for-byte identical or detection accuracy shifts): 2x bicubic when
  `h < 300 AND w < 900`, else 1x (`_UPSCALE_MAX_HEIGHT`/`_UPSCALE_MAX_WIDTH` in `engine.py`).
- `DataDir` (passed via `--dir`) is `%LOCALAPPDATA%\<AppName>` when compiled, `A_ScriptDir` in dev.

**Two implementation details worth keeping:**

- `StopOcrServer()`'s force-kill fallback (reached only if the graceful `ocr_stop.txt` path misses its
  600ms window; the normal graceful path measures ~450ms) runs `taskkill.exe /F /T /PID <pid>` before
  falling back to `ProcessClose`. PyInstaller's onefile build launches a bootloader process that
  spawns a child process for the actual Python code (two OS PIDs per run), so `ProcessClose` on the
  tracked bootloader PID alone would orphan the child. `/T` kills the tree.
- `.github/workflows/release.yml` builds the OCR exe (`pip install .[dev]`, then
  `pyinstaller --onefile` inside `ocr/`) and copies it to `macro/ocr_server.exe` before the Ahk2Exe
  step so `FileInstall` finds it.

**Dev-loop implication:** `FileInstall` only runs when `A_IsCompiled`, so a source/dev run reads
`macro/ocr_server.exe` directly (`RuntimeDir` is `A_ScriptDir` when not compiled). It must be built
once per `ocr/BUILD.md` and copied there before OCR detection works from a source checkout, exactly
like `remote/agent`'s `go build`. It is gitignored, not committed.

**Deferred (Phase 1b):** `rapidfuzz` fuzzy matching (replacing `TextContainsPartialMatch`'s
substring-window heuristic), OpenCV template/color matching as a new detection mode (needs its own
protocol and config-schema extension), benchmarking alternate OCR engines, and CI-automating the
PyInstaller build outside a tagged release.

## Codex delegation

Delegate implementation to Codex through the repo wrapper `tools/codex-delegate.mjs` (it runs
`codex exec --json` and surfaces Codex's full reasoning trace, which the `/codex:rescue` plugin
command drops) instead of writing it yourself. Pick the model by how hard the task is:

- Simple / low-reasoning subtasks (bug fixes, boilerplate, simple refactors, writing tests,
  repetitive changes) -> gpt-5.6-luna:

      node tools/codex-delegate.mjs --model gpt-5.6-luna --effort <level> "<concrete, clearly scoped task>"

- Complex logic (non-trivial algorithms, tricky state handling, multi-step refactors) ->
  gpt-5.6-terra. Do NOT implement complex logic yourself anymore, delegate it to terra:

      node tools/codex-delegate.mjs --model gpt-5.6-terra --effort <level> "<concrete, clearly scoped task>"

You choose `--effort` yourself (none|minimal|low|medium|high|xhigh) to match the task's difficulty:
lower for simple edits, higher for subtle logic.

It runs Codex in the workspace-write sandbox so Codex can implement the change; add `--read-only` for
investigations that must not touch files. The wrapper streams Codex's full reasoning live into a
per-model Markdown file in the repo root (`codex-reasoning-<model>.md`, gitignored; override with
`--reasoning-file <path>`). It does NOT open that file in VS Code by default; pass `--open` to have
it open its own tab on first update (`code -r`, best-effort, per model). New runs APPEND a dated
section; delete the file to clear it. If that file is already held by another running instance, the
run streams to a separate temp file instead, so simultaneous runs never interleave.

After a workspace-write delegation the wrapper AUTO-REVIEWS the change: it detects which files the
delegation touched and runs a read-only review of just those files with the reviewer one tier up
(luna -> terra, terra -> terra). To stdout, and thus into this chat, it prints the delegation answer
plus the auto-review findings and both reasoning-file paths. Relay those as-is (do NOT paste the
reasoning into the chat), then act on the findings. `--no-review` skips the auto-review (e.g. to
bundle several delegations before one review); `--review-effort <level>` sets the review's effort.

Still implement yourself (do NOT delegate): architecture decisions, security-relevant code (auth,
data processing, payments), and anything where a mistake would be especially costly or hard to
reverse. Also implement yourself if Codex tokens are exhausted and delegation is not possible; in
that case proceed directly without waiting for the budget to recover.

For work you implemented YOURSELF, run the review manually with `--read-only` and gpt-5.6-terra,
scoped to ONLY your change (the files from `git status` and their immediate context, the change, not
whole files):

      node tools/codex-delegate.mjs --read-only --model gpt-5.6-terra --effort <level> "Review the CHANGES to <the changed file(s)> and their immediate context. Focus on what you added or modified; do NOT re-report unrelated pre-existing code. Report issues with file:line; if none, say it looks good. Do not modify files."

Choose `--effort` by how subtle the change is. For a broader sweep over ALL uncommitted changes at
once, use gpt-5.6-terra (this is also what the stop-gate runs at turn-end). Summarize the review's
findings in the chat; its reasoning streams to the reasoning file, not the chat. The
`git -c safe.directory='*'` prefix is required for git commands inside the Codex sandbox, which runs
as a different OS user and otherwise aborts with "dubious ownership".

`model_reasoning_summary` / `show_raw_agent_reasoning` in `~/.codex/config.toml` control whether Codex
produces a human-readable thought process at all. They are currently commented out (disabled, to save
tokens); re-enable them there if someone needs to read the reasoning file.

The native `codex exec review --uncommitted -c model="..."` reviewer is an alternative that yields
more structured P1/P2 findings, but it cannot scope to a single file, cannot combine `--uncommitted`
with a focus prompt, and does not stream reasoning to the reasoning file.

When enabled, the stop-time review gate also runs a final `/codex:review` on the global default
(`gpt-5.6-terra` / `high`) before each turn ends. (`/codex:setup --enable-review-gate` /
`--disable-review-gate` toggles it.)

### Presenting Codex output

Render relayed Codex output as clean Markdown; never paste the raw runtime log:

- Drop the transient `[codex] Running command: ...` / `[codex] Command completed ...` lines; those
  are runtime noise.
- Reasoning placement: delegation AND reviews both run through `tools/codex-delegate.mjs`, which
  streams reasoning to the reasoning file, NOT the chat. In the chat, relay only the wrapper's answer
  (findings) and the reasoning-file path. (If you fall back to the native `codex exec review`, its
  reasoning renders inline as a `Reasoning:` section: surface that under a plain **Reasoning**
  heading, no emoji.)
- Render the final answer / review findings as normal Markdown (headings, bullet lists, fenced code,
  `file:line` links).
- Keep the substance of reasoning and findings verbatim: do not paraphrase or shorten it. Only the
  runtime progress log may be omitted.

For a live, terminal-native "thinking" stream, the user can also run Codex interactively (`codex`
with no subcommand) in a real terminal, or watch the reasoning file live (VS Code preview,
`tail -f`).
