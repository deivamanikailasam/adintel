# Running AdIntel for a team on one machine

The local setup guide gets one person running in terminals. This page turns the same machine into a small
always-on server for a team: services that start on boot and restart on failure, and HTTPS for colleagues
on the office network.

## 1. Supervised services

```bash
make frontend-build                 # the production Angular build that the edge serves
scripts/install_services.sh --print # review the generated launchd/systemd files in deploy/services/out/
scripts/install_services.sh         # install and start
```

| | macOS (launchd agents) | Linux (systemd units) |
|-|------------------------|-----------------------|
| Services | mlx-small, mlx-frontier, api, worker, executor, scheduler | api, worker, executor, scheduler (models via a [model-server profile](model-servers.md)) |
| Start | at login, `KeepAlive` on crash, 10 s throttle | at boot, `Restart=on-failure` |
| Logs | `var/log/<service>.log` | `journalctl -u adintel-api` |
| Status | `launchctl list \| grep com.adintel` | `systemctl status 'adintel-*'` |
| Isolation | one OS user | `adintel` and **`adintel-exec`** users, `ProtectSystem=strict`, `NoNewPrivileges`, no capabilities |
| Credential keys | `secrets/.keys` (same user — separation is by policy) | `LoadCredential=`: only the executor unit receives `write.key` (separation enforced by the OS) |

Linux one-time setup: `sudo useradd -r adintel && sudo useradd -r adintel-exec`, give both read access to
the checkout, put the keys in `/etc/adintel/keys/` (`root:root 0600`; systemd hands them to the right unit).
On macOS keep the laptop from sleeping while it serves (`caffeinate -s` or Energy settings) — the scheduler's
missed jobs run on wake (`misfire_grace_time`), but nightly runs would be late.

Docker infrastructure (`make up`) restarts on its own (`restart: unless-stopped`); enable Docker to start at
login/boot.

## 2. HTTPS for colleagues (Caddy edge)

```bash
ADINTEL_HOST=adintel.office.lan docker compose -f deploy/docker-compose.yml --profile edge up -d
```

- Serves the built web app and proxies `/api` and `/scim` to the API (which itself listens on 127.0.0.1
  only). Server-sent events stream without buffering.
- `/metrics`, the Alertmanager webhook and the interactive API docs are **not** reachable from the network.
- Certificates: `ADINTEL_TLS=internal` (default) uses Caddy's own CA — install its root once on each
  colleague's machine (`docker compose ... exec caddy cat /data/caddy/pki/authorities/local/root.crt`).
  With a public DNS name, set `ADINTEL_TLS=` (empty) and `ADINTEL_ACME_EMAIL` for a Let's Encrypt
  certificate.
- Sign-in: add `https://<host>/*` as a valid redirect URI of the `adintel-frontend` client in Keycloak and
  the Keycloak origin to `connect-src` in `frontend/src/index.html`; set `ADINTEL_CORS_ORIGINS` only if the
  app is served from a different origin than the API (it isn't, through the edge).
- Firewall: allow 443 (and 80 for redirects/ACME) from the office network only.

## 3. Checklist before calling it "production on one machine"

- [ ] `ADINTEL_AUTH_MODE=oidc`, dev login disabled, MFA on in the identity provider
- [ ] `ADINTEL_SECRETS_REQUIRE_ENCRYPTION=true`, keys escrowed
- [ ] `ADINTEL_OFFLINE=true` or an egress allowlist; `adintel egress-check` all allowed
- [ ] `adintel weights verify` clean; `adintel migrate --check` clean
- [ ] Backups scheduled (`scripts/backup.sh` nightly) and a restore drill done
- [ ] Alerts reach a person ([on-call](../12-operations/on-call.md)); disk encryption (FileVault/LUKS) on
