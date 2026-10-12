# 0057 — Second gap review: what a one-machine enterprise deployment still needed

**In one sentence:** a second pass over "production, enterprise-grade, on a local machine" found seven
missing pieces; each was added in its own change and the readiness matrix now lists them with evidence.

| Change | Gap | Now |
|--------|-----|-----|
| [0051](0051-bulkheads.md) | Concurrent calls piled up on a single-slot local model server | Per-tier bulkheads, fast fallback; request size limit |
| [0052](0052-shadow-mode.md) | The promotion gate's "3-day shadow" step had no implementation | Champion/challenger shadow mode with a ready verdict |
| [0053](0053-egress-offline-weights.md) | "Runs locally" was not enforced; base weights not pinned | Offline mode / egress allowlist; weight-file SHA-256 lock |
| [0054](0054-encrypted-secrets.md) | Credentials in plaintext on disk | AES-256-GCM, one key per scope |
| [0055](0055-scim.md) | Users added and removed by hand; old tokens kept old roles | SCIM 2.0; deactivation effective on next request |
| [0056](0056-services-edge.md) | Processes ran in terminals; no HTTPS for colleagues | launchd/systemd services, hardened; Caddy HTTPS edge |

Checks after the review: ruff, mypy --strict, ~300 tests at 89 % coverage (gate 85 %), frontend build and
tests, 10 eval suites and the promotion gate — all pass.

## Why it matters (layman's terms)

The first review asked "does it have every feature an enterprise expects?"; this one asked "would it
survive being the team's real server on one machine?" — busy moments, a new model, no internet, a stolen
disk, a leaver, a reboot. Each of those now has an answer in the code.
