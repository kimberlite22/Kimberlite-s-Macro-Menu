# Remote Access Protocol (source of truth)

This document defines the wire contract for the "remote access initiative" described in
`CLAUDE.md`. It is the single source of truth shared by the Go agent (`remote/agent/`) and the
TypeScript backend (`remote/server/`). Keep the command enum and DTO shapes here in sync with the
code on both sides.

    [Browser / phone] --HTTPS--> [Backend + website] <--outbound-- [Local agent] <--files--> [AHK macro]

The home PC only makes OUTBOUND connections (the agent phones home). The AHK macro does NO
networking: it only reads/writes local files (the remote bridge). All networking and auth live in
the agent and the backend.

## 1. Local file bridge (agent <-> AHK macro)

Defined by `macro/remote_bridge.ahk`. The agent is the "external agent" that module was built for.
All files live next to `tower_defense_macro_gui.ahk` (the macro's `A_ScriptDir`). The agent is told
this directory via `--macro-dir` / config.

- `remote_status.json` (macro -> agent): flat JSON snapshot, written ~1x/sec. UTF-8 without BOM.
  The `timestamp` field ("yyyy-MM-dd HH:mm:ss", local time) doubles as a heartbeat; a stale
  timestamp means the macro is offline. Fields (schema 1):
  `schema, timestamp, state, running, paused, dryRun, activePreset, runningPreset, queuedPreset,
  currentMap, currentScreen, currentStep, cycleCount, stepRepeatCount, startRepeatCount,
  victoryCount, defeatCount`.
- `remote_cmd.txt` (agent -> macro): one command `\<token\>|\<TYPE\>|\<arg\>` (arg optional). MUST be
  atomic-published (write `remote_cmd.txt.tmp`, then move over `remote_cmd.txt`). The macro consumes
  (deletes) it on read, so each command runs at most once. A repeated token is acknowledged but not
  re-run.
- `remote_ack.txt` (macro -> agent): `\<token\>|\<ok|error\>|\<message\>` written after handling a
  command. The `token` echoes the command's token.
- `macro_log.txt` (macro -> agent): the human log. The agent tails it (never duplicated into status).

The command whitelist enforced by the macro (`RemoteBridgeApplyCommand`) is exactly:
`PAUSE`, `RESUME`, `STOP`, `SET_ACTIVE_PRESET \<name\>`, `QUEUE_PRESET \<name\>`. There is deliberately
NO remote START. The agent and backend MUST NOT invent any command outside this set.

## 2. Command enum (shared)

The one authoritative set of command types, shared by AHK, Go, and TS:

    PAUSE              # arg: none
    RESUME             # arg: none
    STOP               # arg: none
    SET_ACTIVE_PRESET  # arg: preset name (runs on next start)
    QUEUE_PRESET       # arg: preset name (switch at next cycle boundary, mid-run)

`arg` is a UTF-8 string, max 200 bytes. Only `SET_ACTIVE_PRESET` and `QUEUE_PRESET` use it. The
backend validates `type` is in this set and `arg` length before enqueuing; the macro re-validates the
preset name exists before acting. The channel is UNTRUSTED: no raw coordinates, keystrokes, scripts,
or arbitrary preset data ever cross it.

## 3. Agent <-> Backend HTTP contract

Base URL configured on the agent (e.g. `https://example.com`). All bodies are JSON
(`Content-Type: application/json`). All timestamps are RFC 3339 / ISO 8601 UTC unless noted.

### 3.1 Auth

- Pairing uses a short-lived, single-use, user-generated **pair code** (no token yet).
- Every other agent request carries `Authorization: Bearer \<deviceToken\>`. The backend stores only a
  hash of the token; the plaintext is shown to the agent once at pairing and saved locally by the
  agent. A revoked device (its `revokedAt` set) is rejected with 401.

### 3.2 `POST /api/agent/pair`  (no auth)

Redeem a one-time pair code for a device token.

    Request:  { "code": "\<pair-code\>", "hostname": "\<machine name\>", "agentVersion": "\<semver\>",
                "os": "\<os string\>" }
    200:      { "deviceToken": "\<opaque secret\>", "deviceId": "\<id\>", "deviceName": "\<name\>" }
    400:      { "error": "invalid_request" }
    401/410:  { "error": "invalid_or_expired_code" }

The code is consumed (single use) on success. `deviceName` defaults to `hostname` if the user did not
name the device when generating the code.

### 3.3 `GET /api/agent/commands?wait=\<seconds\>`  (Bearer device token)

Long-poll for pending commands. The server holds the request up to `wait` seconds (clamped
server-side, default 25, max 55) and returns as soon as one or more commands are pending, else an
empty list on timeout. The agent re-polls immediately after each response (standard long-poll loop).

    200: { "commands": [ { "id": "\<cmdId\>", "type": "\<CommandType\>", "arg": "\<string\>" } ] }

Returning a command marks it `delivered` server-side (with a lease); if it is not acked within the
lease it may be redelivered, and after `COMMAND_MAX_AGE_SECONDS` it is expired. The agent applies each
command via the file bridge and reports the ack (3.4). Delivery is at-least-once; the AHK token dedup
(`RemoteBridgeLastCmdToken`) + delete-on-read make application at-most-once within a macro session, so
the effect is effectively exactly-once per command id. Caveat: that dedup token is in memory, so an
apply -> lost-ack -> macro-restart -> redelivery sequence could re-apply a command; the whitelisted
actions are near-idempotent (a repeated `QUEUE_PRESET` merely re-queues), which bounds the impact.

### 3.4 `POST /api/agent/report`  (Bearer device token)

The agent's single "phone-home" write channel: heartbeat + status snapshot, new log lines, and
command acks. Any of the three may be omitted on a given call. The agent calls this ~1x/sec while the
macro is active (and at least every few seconds as a heartbeat) and immediately after acking a
command.

    Request: {
      "status": {                      # optional; the parsed remote_status.json plus agent fields
        "macroOnline": true,           # agent-derived: is remote_status.json fresh?
        "schema": 1, "timestamp": "...", "state": "running|paused|stopped",
        "running": true, "paused": false, "dryRun": false,
        "activePreset": "...", "runningPreset": "...", "queuedPreset": "...",
        "currentMap": "...", "currentScreen": "...", "currentStep": "...",
        "cycleCount": 0, "stepRepeatCount": 0, "startRepeatCount": 0,
        "victoryCount": 0, "defeatCount": 0
      },
      "logs": [ { "seq": 1234, "line": "..." } ],   # optional; monotonic per-device seq, new lines only
      "acks": [ { "commandId": "\<id\>", "ok": true, "message": "..." } ]  # optional
    }
    200: { "ok": true, "nextPollMs": 1000, "latestAgentVersion": "0.1.0" }   # hints; latestAgentVersion optional

The server updates the device's `lastSeenAt` on every authenticated agent request; the browser side
derives "agent online" from `lastSeenAt` freshness and "macro online" from `status.macroOnline` +
`status.timestamp`.

### 3.5 `GET /api/agent/version`  (no auth)

Public update metadata. Returns `{ "latest": "x.y.z", "minSupported": "x.y.z" }`. The agent checks
this at startup and also reads `latestAgentVersion` from each report response, and logs a one-time
warning when a newer version is available. The agent does NOT self-update (that additionally requires
code-signing the binary; see DEPLOY.md).

## 4. Browser <-> Backend HTTP contract (authenticated user)

Auth is a logged-in user session (better-auth: email + password, plus optional TOTP 2FA). All
`/api/*` browser routes require a valid session; every row is scoped to the session's `userId`
(multi-tenant). A user may only see/act on their own devices.

- `POST /api/auth/*` — handled by better-auth (sign-up, sign-in, sign-out, session). TOTP 2FA lives
  under `POST /api/auth/two-factor/*` (`enable`, `verify-totp`, `verify-backup-code`, `disable`,
  `generate-backup-codes`). A sign-in for a 2FA-enabled user returns `{ twoFactorRedirect: true }` and
  no session until the challenge is completed. Auth endpoints have their own brute-force rate limits.
- `GET  /api/me` — current user summary `{ id, email, twoFactorEnabled }`.
- `GET  /api/audit?limit=\<n\>` — recent audit entries for the user `[{ id, action, detail, deviceId,
  ip, createdAt }]` (pairing, revoke, command enqueue, pair-code creation).
- `GET  /api/devices` — `[{ id, name, agentOnline, macroOnline, lastSeenAt, revokedAt }]`.
- `POST /api/devices/pair-code` — body `{ deviceName? }`; returns `{ code, expiresAt }` (single use,
  short TTL). Shown to the user to paste into `agent --pair`.
- `POST /api/devices/:id/revoke` — revoke the device token (agent must re-pair).
- `GET  /api/devices/:id/status` — latest status snapshot (or `null` if none yet).
- `GET  /api/devices/:id/logs?since=\<id\>&limit=\<n\>` — `{ lines: [{ id, seq, line, at }], lastId }`.
  The browser cursor is the backend row id (a gap-free, monotonic bigserial), NOT the agent's per-device
  `seq`. The agent `seq` is used only for idempotent ingest dedup (unique on `(deviceId, seq)`); the
  browser pages by passing the previous response's `lastId` back as `since`.
- `POST /api/devices/:id/commands` — body `{ type, arg? }`; validates against the whitelist and the
  device ownership (rejects a revoked device); returns `{ commandId }`. Rate-limited and audit-logged.
- `GET  /api/devices/:id/commands/:commandId` — `{ id, type, arg, status, ok, message, createdAt,
  deliveredAt, ackedAt }` for the UI to show the result of an issued command.

Operations (no auth): `GET /health` (liveness + active DB driver + uptime) and `GET /health/ready`
(readiness: 200 only when a trivial DB query succeeds, else 503). An app-wide per-IP rate limiter
guards everything except `/health*`; auth endpoints have their own stricter limits (see section 4).

## 5. Data model (PostgreSQL dialect: PGlite in dev, Postgres in prod)

better-auth owns the user/session/account/verification tables plus the twoFactor table (and
`user.twoFactorEnabled`). The implementation uses the PostgreSQL dialect throughout via Drizzle:
PGlite (pure-WASM, no native build) in development, node-postgres in production — the schema and code
are identical for both. Application tables (all app rows carry `userId` for tenant isolation):

- `devices(id, userId, name, tokenHash, hostname, os, agentVersion, createdAt, lastSeenAt, revokedAt)`
- `pairing_codes(id, userId, codeHash, deviceName, expiresAt, usedAt, createdAt)`
- `device_status(deviceId PK, userId, snapshotJson, macroOnline, macroTimestamp, receivedAt)`
- `logs(id, deviceId, userId, seq, line, receivedAt)`  — seq is monotonic per device
- `commands(id, deviceId, userId, type, arg, status, ok, message, createdAt, deliveredAt, ackedAt)`
      status in {pending, delivered, acked, error, expired}
- `audit(id, userId, deviceId, action, detail, ip, createdAt)`

Tokens and pairing codes are stored ONLY as hashes (never plaintext). Device tokens: random 32 bytes,
base64url; hashed with SHA-256 for lookup (the token itself is high-entropy, so a fast hash keyed by a
prefix index is acceptable; passwords go through better-auth's slow hash). Pairing codes: short,
human-pasteable, single-use, short TTL, also stored hashed.

## 6. Phasing (status)

- Phase 1 (DONE) — Go agent (`remote/agent/`), stdlib-only single `.exe`; file bridge, config,
  pairing, outbound long-poll + report. Validated end to end.
- Phase 2 (DONE) — backend (`remote/server/`): Fastify + Drizzle + better-auth implementing sections 3
  and 4, plus the web MVP. (Uses the Postgres dialect from the start; see section 5.)
- Phase 3 (DONE) — multi-tenant isolation, TOTP 2FA, app + auth rate limiting, audit log, device-token
  revocation, and an agent version/update-check (self-update deferred; needs code signing).
- Phase 4 (DONE) — operations: `/health` + `/health/ready`, DB backup script (`scripts/backup.mjs`),
  env-based secret management (`.env.example`), and the deployment guide (`DEPLOY.md`: Caddy /
  Cloudflare Tunnel, Postgres).

The only remaining, operator-dependent items are cloud deployment (a domain + TLS) and, if fully
automated agent self-update is desired, a Windows code-signing certificate.
