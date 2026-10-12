# Data protection impact assessment — summary

**Assessment date:** 2026-10-12 · **Owner:** Product owner · **Review:** annually, or on any change of model
provider, autonomy level or data category.

## Is a DPIA required?

AdIntel uses new technology (LLM agents) over business data that incidentally contains personal data, so a
DPIA is carried out as good practice. It does **not** profile individuals, make decisions with legal or
similarly significant effects on people, or process special-category data at scale.

## Processing described

Nightly analysis of advertising performance per brand; drafting of reports; proposals for budget changes
that named agency staff approve; a chat assistant for staff. See the [records of processing](records-of-processing.md).

## Necessity and proportionality

- Data minimisation: aggregates per ad set and day; no audience-level or user-level ad data is ingested.
- PII detected in model inputs is redacted before any model call (`security/pii.py`).
- Retention periods are declared per collection and enforced daily.
- Staff can export or erase their data (pseudonymisation keeps the accountability record).

## Risks and measures

| Risk | Likelihood × impact (before) | Measures | Residual |
|------|------------------------------|----------|----------|
| One agency's data shown to another | Possible × high | Three-layer tenant isolation, 0-leakage eval gate, P1 alert on violation | Low |
| Model provider retains or trains on data | Possible × high | Local inference by default; production providers only with no-training/zero-retention terms, enforced in code (ADR L-15) | Low |
| Prompt injection in campaign names/documents leads to harmful action | Possible × high | Fencing, injection flag → quarantine, optimizer has no tools, executor has no model, human approval | Low |
| Inaccurate report numbers mislead a client | Likely × medium | Numeric grounding check; template fallback; numbers only from the database | Low |
| Excessive retention of staff data | Possible × low | Declared retention, daily purge, erasure | Low |
| Unauthorised access via stolen credentials | Possible × high | SSO with MFA, short-lived tokens, least-privilege roles, audit | Low–medium (depends on IdP configuration) |

## Conclusion

Residual risk is **low**; processing may proceed. No prior consultation with a supervisory authority is
needed. Conditions: MFA enforced in the identity provider; DPA signed; this DPIA reviewed annually.
