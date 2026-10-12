# 0056 — From "running in my terminals" to "the team's server"

**In one sentence:** AdIntel can now run on one machine as proper background services that start by
themselves and restart after a crash, and colleagues can reach it securely over HTTPS on the office network.

## What changed

- `deploy/services/services.txt` + `scripts/install_services.sh [--print|--uninstall]` — generates and
  installs launchd agents (macOS: both mlx servers + api, worker, executor, scheduler; logs in `var/log/`)
  or systemd units (Linux: hardened with `ProtectSystem=strict`, `NoNewPrivileges`, no capabilities; the
  executor runs as its own `adintel-exec` user and is the only unit given `write.key` via
  `LoadCredential=`). `make services-install`.
- `security/secret_crypto.py` — reads keys from `$CREDENTIALS_DIRECTORY` (systemd credentials).
- `deploy/caddy/Caddyfile` + Compose profile `edge` (`make edge`) — HTTPS (internal CA or Let's Encrypt),
  serves the built web app, proxies `/api` (streaming-safe) and `/scim`, blocks `/metrics`, the alert webhook
  and API docs from the network, security headers, JSON access log with rotation.
- `docs/13-setup/team-access.md` — setup, certificates, sign-in redirect URIs, firewall, and a "production on
  one machine" checklist.

## Why it matters (layman's terms)

A shop isn't open if the owner has to unlock the door by hand every morning. Now the system opens itself
when the computer starts, gets back up if it trips, and colleagues come in through a proper front door with
a lock (HTTPS) — while the staff-only rooms stay locked from the street.
