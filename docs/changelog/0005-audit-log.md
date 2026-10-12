# 0005 — Immutable, hash-chained audit log

**In one sentence:** every important action now goes into a ledger where each page is sealed with a
fingerprint of the page before it, so nobody can quietly rewrite history.

## What changed

- `src/adintel/audit/chain.py` — `AuditLog.append(...)` writes an entry containing who did what
  (a named person, or an agent *and its exact model version*), to which object, in which run, plus
  the previous entry's hash. `AuditLog.verify()` and `verify_all_tenants()` re-compute every hash.
- `docs/10-audit/audit-and-reproducibility.md` — what is deterministic, what is reproducible instead,
  and how the audit trail is hardened in production.

## Why it matters (layman's terms)

When a client asks "who approved moving $200 a day and why?", the answer has to be provable. A normal
database table can be edited by anyone with access. Here, changing even one old entry breaks the
fingerprint chain from that point on, and the nightly check raises a top-priority alert. We tested
three ways of cheating — editing, deleting, and editing-then-recomputing the fingerprint — and all
three are caught.
