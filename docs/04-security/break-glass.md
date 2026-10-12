# Break-glass (emergency elevated access)

Nobody holds standing admin rights "just in case". When someone needs more access — every brand during an
incident, or the kill switches at 3 a.m. — they ask for it, for a limited time, and it is recorded.

| | Normal | Emergency |
|-|--------|-----------|
| Who can request | any staff member | any staff member |
| Activation | a **different**, non-elevated admin approves | immediately |
| Maximum duration | 4 hours | 60 minutes |
| Alert | P3 to security on approval | **P1 page to security** on activation |
| Afterwards | — | grant flagged `review_required` for the post-incident review |

Scopes: `all_brands` (see every brand in the tenant) and `admin` (governance console, kill switches, audit).

What elevation **never** does:

- grant authority to spend money — approvals use the approver's stored roles and approval limit, which a
  grant doesn't touch; `head_of_performance` and other money roles cannot be requested;
- allow destructive or policy actions — user erasure, feature-flag changes and SCIM token issuing are refused
  while elevated;
- outlive its expiry — access ends at `expires_at` on the next request; the scheduler then marks the grant
  expired in the record (every 5 minutes).

API: `POST /admin/break-glass/requests` `{scopes, reason (≥ 10 chars), ticket, minutes, emergency}`,
`POST /admin/break-glass/{id}/approve` (admin), `POST /admin/break-glass/{id}/revoke` (holder or admin),
`GET /admin/break-glass` (admin). Audit actions: `break_glass.requested|approved|revoked|expired`.
Tests: `tests/api/test_break_glass.py`.
