# Anime Expedition - Remote Access

Remote monitoring and safe control of the Anime Expedition macro from a browser or phone, built on the
"phone-home" architecture described in the repository `CLAUDE.md`.

    [Browser / phone] --HTTPS--> [Backend + website] <--outbound-- [Local agent] <--files--> [AHK macro]
       (login, 2FA)             (accounts, API, DB)     (only net I/O)  (Go, single .exe)   (this repo)

- The home PC only makes OUTBOUND connections (the agent "phones home"). No port forwarding, no inbound
  firewall holes.
- The AHK macro does NO networking. It reads/writes local files only (the remote bridge in
  `macro/remote_bridge.ahk`), exactly like the OCR helper. All networking and auth live in the agent and
  the backend.
- The command channel is a fixed whitelist (`PAUSE`, `RESUME`, `STOP`, `SET_ACTIVE_PRESET`,
  `QUEUE_PRESET`) - never raw coordinates, keystrokes, or scripts.

See `PROTOCOL.md` for the exact wire contract, and `DEPLOY.md` for production deployment.

## Components

| Path            | What it is                                                                    |
|-----------------|-------------------------------------------------------------------------------|
| `remote/agent/`  | The local agent (Go, standard library only, single `.exe`). Bridges the macro files to the backend over outbound HTTPS. |
| `remote/server/` | The backend + web UI (Node + Fastify + Drizzle + better-auth). Serves the API, the browser dashboard, accounts/2FA, and stores per-device status/logs/commands. |
| `remote/PROTOCOL.md` | The authoritative agent<->backend + file-bridge contract. |
| `remote/DEPLOY.md`   | Production deployment (TLS via Caddy or Cloudflare Tunnel, Postgres, backups, monitoring). |

The macro side (already in the repo) is `macro/remote_bridge.ahk`, enabled with the "Enable remote
bridge" checkbox on the General tab.

## Requirements

- Node.js >= 24 (the backend uses the built-in `node:sqlite`-free PGlite driver in dev and `pg` in prod;
  no native build step is required).
- Go >= 1.26 to build the agent (only needed to produce the `.exe`; end users just run the binary).

## Quick start (all local, single machine)

1. Backend
   ```sh
   cd remote/server
   npm install
   cp .env.example .env            # then set AUTH_SECRET (see below); leave DATABASE_URL empty for dev
   npm run db:migrate              # create the schema in the dev PGlite database (./.data)
   npm run dev                     # starts on http://localhost:8787
   ```
   Generate a secret for `.env`:
   ```sh
   node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
   ```

2. Create your account
   - Open http://localhost:8787, choose "Create account", and sign in. (Optionally enable two-factor
     authentication from the dashboard's Security card.)

3. Build the agent
   ```sh
   cd remote/agent
   go build -o animeexpedition-agent.exe .
   ```

4. Pair the agent with your account
   - In the dashboard click "Add device" to get a one-time pairing code (valid ~10 minutes, single use).
   - On the PC running the macro:
     ```sh
     animeexpedition-agent.exe --server http://localhost:8787 --pair <CODE> --macro-dir "C:\path\to\macro"
     ```
     `--macro-dir` is the folder containing `tower_defense_macro_gui.ahk` (where the bridge files live).
     Pairing stores a device token in `%APPDATA%\AnimeExpeditionAgent\config.json` (0600).

5. Run the agent
   ```sh
   animeexpedition-agent.exe
   ```
   Enable the "Enable remote bridge" checkbox in the macro (General tab). The dashboard now shows live
   status + logs and offers the whitelisted controls.

## Agent command reference

```
animeexpedition-agent.exe [flags]
  --config <path>       config file (default %APPDATA%\AnimeExpeditionAgent\config.json)
  --server <url>        backend base URL (saved on --pair)
  --pair <code>         redeem a one-time pairing code, save the device token, then exit
  --macro-dir <path>    directory of the macro (where the bridge files live)
  --device-name <name>  local device name override
  --poll-wait <seconds> command long-poll wait (default 25)
  --status              print the parsed macro status once and exit (debugging)
  --version             print the agent version and exit
```

## Security summary

- Passwords and sessions are handled by better-auth (never hand-rolled). Optional TOTP two-factor.
- Device tokens and pairing codes are stored ONLY as SHA-256 hashes; plaintext is shown once.
- Every browser API row is scoped to the logged-in user (multi-tenant isolation).
- Auth endpoints have their own brute-force rate limiting; the app has an IP rate limiter on top.
- Sensitive actions (pairing, revoke, command enqueue, pair-code creation) are written to an audit log.
- Revoking a device immediately invalidates its token.

## Testing

- Backend unit/integration tests: `cd remote/server && npm test`
- Agent tests: `cd remote/agent && go test ./...`

## Known limitations / operator responsibilities

- Running a public service that automates a Roblox game likely violates Roblox ToS and can get accounts
  banned. Understand the risk before exposing this beyond your own machine.
- The long-poll notifier is in-process (single backend node). Running multiple backend instances needs a
  shared notification bus (not yet implemented).
- The agent detects and logs when a newer version is available; it does NOT self-update. Automated
  self-update additionally requires code-signing the `.exe` (operator-provided certificate).
