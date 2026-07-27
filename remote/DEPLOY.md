# Deployment (production)

This guide takes the `remote/server` backend from the local dev setup to a public, TLS-protected,
multi-user deployment. The design keeps the home PC outbound-only, so nothing here needs inbound ports
on the machine running the macro.

## 1. Prerequisites

- A small Linux (or Windows) server/VM reachable from the internet, OR a Cloudflare Tunnel (no public
  IP required).
- Node.js >= 24 on that server.
- PostgreSQL 14+ (managed or self-hosted). PGlite is for development only; production uses Postgres.

## 2. Configuration (environment)

Copy `.env.example` and set real values. Do NOT commit `.env`.

| Variable                | Production value                                                        |
|-------------------------|-------------------------------------------------------------------------|
| `NODE_ENV`              | `production` (enables secure cookies; requires `AUTH_SECRET`).          |
| `HOST` / `PORT`         | `127.0.0.1` / `8787` - bind to localhost; the reverse proxy faces the internet. |
| `PUBLIC_URL`            | your real HTTPS origin, e.g. `https://macro.example.com`.               |
| `AUTH_SECRET`           | 32+ random bytes: `node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"`. |
| `DATABASE_URL`          | `postgres://user:pass@host:5432/anime_expedition` (switches off PGlite).|
| `TRUST_PROXY`           | `true` ONLY because a trusted reverse proxy (Caddy / Cloudflare) sits in front. Leave unset/false otherwise, or the IP rate limiter and audit IPs can be spoofed. |
| `RATE_LIMIT_MAX` / `RATE_LIMIT_WINDOW` | tune if needed (defaults 300 / "1 minute" per IP).         |
| `AGENT_LATEST_VERSION`  | the newest agent version you publish, so older agents log an update hint.|

## 3. Database

```sh
cd remote/server
npm ci
DATABASE_URL=postgres://... npm run db:migrate     # applies drizzle/*.sql to Postgres
```
The same migrations run against Postgres and PGlite (identical Postgres dialect).

## 4. Run the backend

```sh
npm run build           # tsc -> dist/
NODE_ENV=production node dist/index.js
```
Keep it running with a process manager. Examples:

- systemd unit (Linux): a `[Service]` running `node /opt/ae/remote/server/dist/index.js` with
  `EnvironmentFile=/opt/ae/remote/server/.env`, `Restart=always`, and a dedicated user.
- pm2 (cross-platform): `pm2 start dist/index.js --name ae-remote`.

## 5. TLS / public exposure (pick one)

### Option A - Caddy (auto-HTTPS)
```
macro.example.com {
    reverse_proxy 127.0.0.1:8787
}
```
Caddy obtains and renews a certificate automatically. Set `TRUST_PROXY=true` (Caddy is the trusted
proxy) and `PUBLIC_URL=https://macro.example.com`.

### Option B - Cloudflare Tunnel (no public IP / no open ports)
```sh
cloudflared tunnel create ae-remote
cloudflared tunnel route dns ae-remote macro.example.com
cloudflared tunnel run --url http://127.0.0.1:8787 ae-remote
```
Cloudflare terminates TLS and forwards to the local backend. Set `TRUST_PROXY=true` and
`PUBLIC_URL=https://macro.example.com`.

In both cases the backend itself stays bound to `127.0.0.1`; only the proxy is public.

## 6. Backups

Use `scripts/backup.mjs` (see below) on a schedule (cron / Task Scheduler):
```sh
node scripts/backup.mjs                 # writes to ./backups, rotates to BACKUP_KEEP (default 14)
```
- With `DATABASE_URL` set it runs `pg_dump -Fc` (needs the Postgres client tools on the host).
- Without it (dev/PGlite) it snapshots the `DATA_DIR` directory.
Store backups off-box (object storage) for real durability.

## 7. Monitoring

- `GET /health` - liveness + which DB driver is active + uptime (no auth; safe to poll).
- `GET /health/ready` - readiness: returns 200 only when a trivial DB query succeeds, else 503. Point
  your uptime monitor / load balancer here.
- The backend logs structured JSON (pino). Ship stdout to your log aggregator.
- The in-app audit log (`/api/audit`, and the dashboard "Recent activity" card) records pairing,
  revocation, and command actions per user.

## 8. Secret management

- Never commit `.env`. Inject secrets via the process environment / secret manager in production
  (`AUTH_SECRET`, `DATABASE_URL`). The app reads `process.env` and only falls back to a `.env` file for
  local dev convenience.
- Rotating `AUTH_SECRET` invalidates existing sessions (users re-login); rotate on suspected compromise.

## 9. Agent distribution and updates

- Build per-OS binaries: `GOOS=windows GOARCH=amd64 go build -o animeexpedition-agent.exe .`
- Publish `AGENT_LATEST_VERSION` so running agents log an update hint.
- Automated self-update is intentionally NOT implemented: doing it safely on Windows also requires
  code-signing the binary (SmartScreen + user trust) with an operator-provided certificate. Until then,
  distribute updates manually.

## 10. Multi-tenant / ToS notes

- All data is keyed by `user_id`; users only see their own devices. TOTP 2FA is available per user.
- A public service that automates a Roblox game likely violates Roblox ToS and risks account bans.
  Communicate this to users and consider restricting sign-ups.
