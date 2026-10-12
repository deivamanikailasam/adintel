# 0065 — Sign-in, refresh and logout work with any standard identity provider

**In one sentence:** AdIntel now asks the company's identity provider where its sign-in, token and logout
addresses are, instead of assuming Keycloak's — so Okta, Entra ID, Auth0 and Cognito work without code changes.

## What changed

- `security/oidc_discovery.py` — reads `<issuer>/.well-known/openid-configuration` (cached 1 hour, refused if
  its `issuer` doesn't match, egress-checked); resolution: explicit setting → discovery → Keycloak layout.
- Backend JWKS URL comes from discovery; `/auth/config` returns the authorization, token and end-session
  endpoints and the logout style.
- Frontend uses those endpoints for the PKCE redirect, token exchange, refresh and logout; `logoutUrl()`
  implements standard RP-initiated logout and Cognito's `/logout` (`client_id` + `logout_uri`).
- New settings `ADINTEL_OIDC_AUTHORIZATION_URL`, `_TOKEN_URL`, `_END_SESSION_URL`, `ADINTEL_OIDC_LOGOUT_STYLE`.
- Docs: security (provider notes, CSP), production promotion (Cognito), `.env.example`.
- Tests: `tests/unit/test_oidc_discovery.py` (Okta-style discovery + caching, Cognito override, fallback,
  mismatched issuer ignored, `/auth/config`); 3 frontend `logoutUrl` specs (11 frontend tests total).

## Why it matters (layman's terms)

Before, the login code had Keycloak's street address written in. Now it looks up the address in the
directory every identity provider publishes, so the same AdIntel works with whichever one the company uses.
