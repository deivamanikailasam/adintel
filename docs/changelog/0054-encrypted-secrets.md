# 0054 — Ad-platform passwords are no longer plain text on disk

**In one sentence:** the local credentials AdIntel uses to read and change ad accounts are now encrypted,
and the key that unlocks "change budgets" credentials is held only by the one process allowed to change
budgets.

## What changed

- `security/secret_crypto.py` — AES-256-GCM per file, random nonce, the secret reference as associated data
  (a file copied to another tenant's or scope's path fails to decrypt), separate keys for `read` and `write`
  from `ADINTEL_SECRETS_KEY_<SCOPE>` or `secrets/.keys/<scope>.key` (must be mode 0600).
- `SecretStore` reads `*.json.enc` first; `put` and `encrypt_existing` for operators;
  `ADINTEL_SECRETS_REQUIRE_ENCRYPTION=true` refuses plaintext files.
- CLI: `adintel secrets keygen | put | encrypt`.
- `scripts/backup.sh` no longer copies the keys next to the ciphertext; key escrow documented.
- Docs: `secrets/README.md`, security controls, readiness matrix (Secrets now ✅).
- Tests: `tests/unit/test_secret_crypto.py` (round trip, moved file, tampering, missing scope key, plaintext
  refusal + migration, key-file permissions).

## Why it matters (layman's terms)

Before, anyone who could copy the laptop's folder could read the keys to the clients' ad accounts. Now
the folder holds locked boxes, and there are two different keys: the one that opens "read the numbers"
boxes, and the one that opens "change the budget" boxes — which only the money-moving component ever holds.
