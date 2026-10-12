# Ad-platform API access plan

**Owner decision.** Go live **platform by platform**, starting on CSV exports (manual execution) and
switching each platform to its live API as its approval arrives — never blocking launch on the slowest
approval. Read access first everywhere; write access only for the executor, only after the platform's
read integration has run cleanly in production for **four weekly cycles**.

```bash
# day 1: everything from exports
ADINTEL_CONNECTORS=csv
# Google Ads approved and contract-tested:
ADINTEL_CONNECTOR_MODES={"google_ads": "live"}
```

Production refuses synthetic data for any platform. A platform switched to `live` still needs
`connectors/live.py` implemented for it, with nightly contract tests against a sandbox/test account
(see [promotion step 5](promotion-to-production.md)).

## What each platform typically requires

Programme names, tiers and review steps change; **check each platform's current developer documentation
before applying** and record the date you checked in the tracker below.

| Platform | Typical prerequisites | Read scope (ingestion) | Write scope (executor only) | Notes |
|----------|----------------------|------------------------|-----------------------------|-------|
| Google Ads | Manager (MCC) account, developer token (test access first, then an access-level application), OAuth client, verified OAuth consent screen | Reporting on customer accounts under the MCC | Campaign budget mutate | Test accounts available for contract tests; standard access has daily operation limits |
| Meta (Facebook/Instagram) | Business Manager with business verification, a Meta app, app review for the advertising permissions, system user tokens | Ads insights read | Ad set budget/status update | App review asks for a screencast of the use case: use staging with a sandbox ad account |
| TikTok | TikTok for Business developer account, Marketing API app approval, advertiser authorisation | Reporting | Ad group budget/status | Approval can take weeks; start on CSV |
| LinkedIn | Marketing Developer Platform / Advertising API access application, LinkedIn Page admin | Ad analytics read | Campaign budget update | Access is granted per use case; describe agency reporting + approved budget changes |
| Amazon Ads | Amazon Ads API registration, Login with Amazon client, advertiser profile authorisation | Reporting (asynchronous reports) | Campaign/ad group budget | Region-specific endpoints (NA/EU/FE) |

## Application checklist (per platform)

- [ ] Business entity verified on the platform; privacy policy and terms URLs public
- [ ] Use-case description: "agency analytics and reporting; budget changes only after named human approval"
      (consistent with the [AI system card](../03-governance/legal/ai-system-card.md))
- [ ] Separate OAuth apps/tokens for **read** (worker) and **write** (executor) where the platform allows it
- [ ] Tokens stored in Secrets Manager (`adintel/<tenant>/<platform>/<scope>`), rotated ≤ 90 days
- [ ] Sandbox/test account for nightly contract tests
- [ ] Rate-limit and quota numbers recorded in `connectors/live.py` and the load model
- [ ] Data-use terms of the platform reviewed against the DPA (no resale, retention limits)
- [ ] Offboarding: OAuth grant revocation steps written in the runbook

## Tracker

| Platform | Applied | Approved (read) | Live read since | Approved (write) | Live write since | Owner |
|----------|---------|-----------------|-----------------|------------------|------------------|-------|
| Google Ads | | | | | | |
| Meta | | | | | | |
| TikTok | | | | | | |
| LinkedIn | | | | | | |
| Amazon Ads | | | | | | |
