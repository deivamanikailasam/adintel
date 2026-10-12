# User provisioning (SCIM 2.0): joiners, movers, leavers

AdIntel never auto-creates users from a login (no just-in-time provisioning). Users are created, changed
and switched off either by a tenant admin or — the enterprise path — by the company's identity provider
over **SCIM 2.0** at `/scim/v2`.

## Set up

```bash
adintel scim token --tenant brightwave        # prints a bearer token ONCE; only its SHA-256 is stored
```

In the identity provider's SCIM / provisioning app: base URL `https://<adintel>/scim/v2`, auth = Bearer
token, attribute mapping `userName ← email`, `name.formatted ← display name`, `externalId ← IdP user id`,
`active ← account enabled`, `roles ← group-to-role mapping` (`viewer`, `account_manager`,
`senior_account_manager`, `head_of_performance`, `admin`). Okta and Microsoft Entra ID offer SCIM
provisioning apps; Keycloak needs a SCIM extension — or test by hand:

```bash
curl -H "Authorization: Bearer $SCIM" -H 'Content-Type: application/scim+json' \
  -d '{"userName":"nia@brightwave.example","name":{"formatted":"Nia"},"roles":[{"value":"account_manager"}]}' \
  http://localhost:8000/scim/v2/Users
```

## What the identity provider can and cannot change

| Attribute | Via SCIM | Why |
|-----------|----------|-----|
| Create / email / name / externalId | ✅ | Identity belongs to the IdP |
| Roles | ✅ (validated against the five AdIntel roles) | Still intersected with token roles at sign-in |
| Active (leaver) | ✅ — `active: false` or `DELETE` deactivates and removes roles | Access ends on the **next request**, not when a token expires |
| Approval limit, brand scope | ❌ (400 `mutability`) | Authority to spend client money is granted inside AdIntel by an admin, audited |
| Hard delete / erasure | ❌ | Approvals must stay attributable; erasure is a [privacy request](privacy-and-data-lifecycle.md) |

Every change is recorded in the tenant's audit log (`user.provisioned`, `user.updated`,
`user.deprovisioned`, `scim.credential_issued`). Tokens are per tenant: one agency's IdP can never see or
change another agency's users.

Supported: `GET/POST /Users`, `GET/PUT/PATCH/DELETE /Users/{id}`, filters `userName eq` and
`externalId eq`, pagination, `/ServiceProviderConfig`. Not supported: Groups, Bulk, sorting, ETags.
