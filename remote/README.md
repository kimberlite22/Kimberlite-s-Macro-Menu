# Macro Menu - Remote Access

Remote monitoring and safe control of Kimberlite's Macro Menu from a browser or phone, built on the
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
bridge" checkbox on the Remote Agent tab.

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
   - **Downloaded release build:** skip this step. `Kimberlites-Macro-Menu.exe` already
     bundles `animeexpedition-agent.exe` (the release workflow builds it and embeds it via
     `FileInstall`, the same mechanism used for the OCR helper) and extracts it next to the installed
     app on every startup, so the Remote Agent tab's "Agent executable" field is prefilled
     automatically.
   - **Source/dev checkout:** build it yourself once so `DefaultRemoteAgentPath` can find it as a
     sibling of `macro/`:
     ```sh
     cd remote/agent
     go build -o animeexpedition-agent.exe .
     ```

4. Pair the agent with your account
   - Pairing is account-based: there is no separate one-time code to generate first. Signing in (or
     registering) with the account IS what creates and pairs the device.
   - **From the macro's GUI (recommended, no command line):** open the "Remote Agent" tab.
     "Agent executable" is already prefilled on a release build (the
     bundled copy) or a dev checkout that has already run `go build` (Browse... otherwise, remembered
     afterward); set the Server URL, choose Log in or Register, enter that account's email and
     password (and a 2FA code if the account has one and it asks for it), and click "Pair". The
     macro itself still does no networking - this launches the SAME agent binary you'd otherwise run by
     hand and reads back its result; see `macro/tower_defense_macro_gui.ahk`'s "REMOTE AGENT SETUP
     WINDOW" section. "Start Agent"/"Stop Agent" on the same tab control the background agent from
     then on.
   - **Or from a terminal:** do NOT put the password in the command itself (`echo "your-password" >
     creds.txt`, `Set-Content -Value "your-password"`, ...) - PowerShell's PSReadLine and most shells'
     history persist every command line to disk, so that would write the password straight into your
     shell history file. Use `Read-Host -AsSecureString` instead, which reads it from a masked prompt
     that history never sees; the snippet below also writes UTF-8 with no byte-order mark, since a BOM
     would otherwise become literal bytes of the "password" the agent reads (this bit the AHK GUI
     during development - see `macro/tower_defense_macro_gui.ahk`'s `RemoteAgentPairClick` comments
     for the full story):
     ```powershell
     $secure = Read-Host "Password" -AsSecureString
     $plain = [Runtime.InteropServices.Marshal]::PtrToStringUni([Runtime.InteropServices.Marshal]::SecureStringToGlobalAllocUnicode($secure))
     [IO.File]::WriteAllText("creds.txt", "$plain`n", [Text.UTF8Encoding]::new($false))
     .\animeexpedition-agent.exe --server http://localhost:8787 --login --email you@example.com --credentials-file creds.txt
     # or --register instead of --login to create a brand new account
     ```
     (append a second `` `n``-separated line before the final one for a TOTP code). The agent
     automatically uses `%LocalAppData%\Kimberlite's Macro Menu`, where the installed app
     keeps its bridge files. `--macro-dir` remains available to override this for source/dev runs.
     Pairing stores a device token in `%APPDATA%\AnimeExpeditionAgent\config.json` (0600); the
     credentials file is deleted by the agent as soon as it has been read.

5. Run the agent
   - From the macro's GUI: click "Start Agent" on the "Remote Agent" tab (it auto-starts right
     after a successful in-app pairing).
   - Or from a terminal:
     ```sh
     animeexpedition-agent.exe
     ```
   Enable the "Enable remote bridge" checkbox in the macro (Remote Agent tab). The dashboard now
   shows live status + logs and offers the whitelisted controls.

## Agent command reference

```
animeexpedition-agent.exe [flags]
  --config <path>       config file (default %APPDATA%\AnimeExpeditionAgent\config.json)
  --server <url>        backend base URL (saved on --login/--register)
  --login               sign in to an existing account and pair this device, then exit
  --register            create a new account and pair this device, then exit
  --email <email>       account email (used with --login/--register)
  --credentials-file <path>  file with the password on line 1 and an optional TOTP code on line 2
                             (used with --login/--register); read once, then deleted
  --auth-result-file <path>  with --login/--register, also write the outcome (one line, never the
                             password or the token) to this file - used by the macro's GUI so it
                             doesn't have to capture stdout
  --macro-dir <path>    bridge data directory (default %LocalAppData%\Kimberlite's Macro Menu)
  --device-name <name>  local device name override
  --poll-wait <seconds> command long-poll wait (default 25)
  --status              print the parsed macro status once and exit (debugging)
  --version             print the agent version and exit
```

## Security summary

- Passwords and sessions are handled by better-auth (never hand-rolled). Optional TOTP two-factor.
- Device tokens are stored ONLY as a SHA-256 hash; the plaintext is shown to the agent once, when the
  device is created.
- Every browser API row is scoped to the logged-in user (multi-tenant isolation).
- Auth endpoints (including the agent's own `/api/agent/auth`) have brute-force rate limiting; the app
  has an IP rate limiter on top.
- Sensitive actions (pairing, revoke, command enqueue) are written to an audit log.
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
