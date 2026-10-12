# 0060 — Emergency access without permanent master keys

**In one sentence:** when someone needs extra access during an incident they can now get it for a few hours
— approved by a second person, or immediately with security paged — and it switches itself off.

## What changed

- `security/break_glass.py` — request → approve (a different, non-elevated admin) → active until expiry;
  emergency path (active at once, ≤ 60 min, P1 to security, review flag); revoke; scheduler marks expired
  grants every 5 minutes; every step audited.
- `api/deps.py` applies active grants to the signed-in principal (`Principal.elevated`); scopes
  `all_brands` and `admin` only.
- Guards: user erasure and feature-flag changes are refused while elevated; money authority is untouched
  because approvals read the approver's stored roles and limit.
- Admin API: request, list, approve, revoke. New collection `access_grants` (7-year retention).
- Docs: `docs/04-security/break-glass.md`, security overview, on-call. Tests: `tests/api/test_break_glass.py`.

## Why it matters (layman's terms)

Fire-alarm glass: you can break it in an emergency and the alarm rings, or ask a colleague for the key —
either way the door relocks by itself in an hour or two, and even with the key you still can't open the safe.
