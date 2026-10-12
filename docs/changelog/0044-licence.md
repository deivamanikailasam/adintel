# 0044 — Who may use AdIntel, and what's inside it

**In one sentence:** AdIntel is now formally proprietary software, and every build proves it contains only
third-party code whose licence allows that.

## What changed

- `LICENSE` — proprietary, all rights reserved; use only under a signed Customer Agreement.
- `pyproject.toml` proprietary classifier + `Private :: Do Not Upload`; frontend `"license": "UNLICENSED"`.
- `config/license-policy.yaml` — allowed (MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0, LGPL…), denied (GPL, AGPL,
  SSPL, BUSL, non-commercial), review-with-exception (EPL, CDDL, CC-BY).
- `scripts/check_licenses.py` — checks every Python distribution and production npm package; fails on denied
  or unknown licences; writes `THIRD_PARTY_NOTICES.md`. Runs in the CI `supply-chain` job on a production-only
  install; the notices ship with the SBOMs. All 115 current packages pass.
- `config/models.yaml` — `weights_license` per tier, to be confirmed on the exact model card before promotion.
- ADR [L-14](../02-decisions/l-14-proprietary-licence-and-dependency-policy.md); README licence section.

## Why it matters (layman's terms)

A buyer's legal team asks "what are we allowed to do with this?" and "is there anything inside that could
force us to give away our own code?". The first answer is now written down; the second is checked by a
machine on every build, with a list of every ingredient and its licence attached.
