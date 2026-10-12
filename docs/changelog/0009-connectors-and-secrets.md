# 0009 — Ad-platform connectors, normaliser and scoped secrets

**In one sentence:** AdIntel can now read data from Google Ads, Meta, TikTok, LinkedIn and Amazon Ads
— locally from realistic simulated accounts — and only one process is ever allowed to hold the keys
that can change a budget.

## What changed

- `connectors/synthetic.py` + `scenarios.py` — simulated ad accounts that return data in each
  platform's **real, messy format** (Google's "micros", Meta's numbers-as-text and nested action lists,
  TikTok's EUR account, LinkedIn's URNs, Amazon's compact dates). They reproduce the three canonical
  brands: Urban Roast's cost spike, Fitely's clean week and NorthPeak's broken tracking. Outages, slow
  responses and new unknown fields can be injected for testing.
- `connectors/normalize.py` — turns every platform's format into one standard daily row in US dollars.
  Unknown fields are flagged as "schema drift", never guessed.
- `connectors/live.py` — the slot where real API clients plug in (same interface).
- `security/secrets.py` — credentials come in two kinds, *read* and *write*. Only the executor process
  may read *write* credentials; the agent worker can read data and call models but cannot change
  anything. `security/secrets_aws.py` is the production version on AWS Secrets Manager.

## Why it matters (layman's terms)

The most important security decision in AdIntel is that the part of the system that "thinks" (and
could in theory be tricked by text hidden in ad data) has **no keys** to change a client's account.
The part that has the keys has no AI in it at all. This commit puts that separation into the code
that hands out credentials.
