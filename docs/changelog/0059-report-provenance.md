# 0059 — Anyone can check that a report really came from AdIntel, unchanged

**In one sentence:** every client report AdIntel releases is now digitally signed and says plainly that AI
helped draft it, so a client (or auditor) can prove a forwarded copy is genuine and unedited.

## What changed

- `audit/provenance.py` — canonical content hash + Ed25519 signature on every released report (held reports
  are not signed); signed AI-assistance disclosure; key from `ADINTEL_REPORT_SIGNING_KEY` (required in
  staging/production, auto-generated locally in `var/keys`).
- Public endpoints (no login, validity only): `GET /.well-known/adintel-report-key`,
  `GET /verify/reports/{report_id}` (recomputes from the stored report, so database edits are caught too);
  exposed through the Caddy edge.
- `adintel verify-report report.json --public-key key.pem` — offline verification.
- Report page shows the disclosure, signing time, key id and fingerprint.
- Docs: audit, AI system card, threat model T16. Tests: `tests/unit/test_provenance.py`.

## Why it matters (layman's terms)

A report gets forwarded, pasted into slides, printed. Now it carries a wax seal: if anyone changes a single
number, the seal breaks — and you don't need to ask AdIntel to check it, because the seal can be tested with
a public key anyone can download.
