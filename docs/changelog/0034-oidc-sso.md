# 0034 — Enterprise single sign-on (OIDC) with Keycloak locally

**In one sentence:** people can now sign in through a real identity provider (Keycloak on the laptop,
Cognito or any OIDC provider in production) instead of the password-less developer login, and production
refuses to start any other way.

## What changed

- `security/auth.py` — verifies RS256/ES256 tokens against the issuer's JWKS (issuer, audience, expiry,
  required claims). Users must already exist in AdIntel inside the token's tenant; effective roles are the
  intersection of identity-provider roles and AdIntel roles. Approval limits and brand scope stay in AdIntel.
- `ADINTEL_AUTH_MODE=dev|both|oidc` plus `ADINTEL_OIDC_*` settings; staging/production require `oidc`.
- `GET /auth/config` tells the UI which sign-in methods are on.
- `deploy/keycloak/adintel-realm.json` — realm `adintel` with the five roles, a public PKCE client, the
  `adintel-api` audience and `tenant_id` mappers, and the eight seed users (password `adintel-local`).
- Docker Compose gains a `keycloak` service on :8180; the app runs in `both` mode.
- Angular: **Sign in with SSO** button, authorization-code + PKCE redirect, `/auth/callback` page; CSP
  allows the Keycloak origin.
- `tests/unit/test_oidc.py` — valid token, wrong issuer/audience/signature, expired, missing tenant, unknown
- Housekeeping: removed three now-unneeded lint suppressions left by 0033.
  user, cross-tenant user, role escalation attempt, dev token refused in `oidc` mode, production config check.

## Why it matters (layman's terms)

A company badge system, not a guest list. Before, anyone who knew an email address could log in on a
laptop. Now the company's own sign-in system (with its passwords, MFA and leaver process) vouches for the
person, and AdIntel still decides what they may do: being an "admin" in the badge system does not make you
an admin here unless AdIntel also says so. Removing someone in either place removes their access.
