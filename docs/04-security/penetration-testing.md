# Penetration testing and security assurance

**Owner decision:** an **independent external penetration test before production go-live**, then
**annually** and after any change to authentication, tenant isolation, the approval/execution path or the
model gateway. In between, automated testing runs on every pull request.

## Layers of assurance

| Layer | When | What | Where |
|-------|------|------|-------|
| Unit / architecture tests | Every PR | Isolation, executor has no model, approval checks, OIDC refusals, guardrail fails closed | `tests/` |
| Adversarial evals | Every PR | 200 injection cases, cross-tenant leakage, constraint compliance (100% gates) | `evals/` |
| SAST + dependency + image scans | Every PR | bandit, pip-audit, npm audit, Trivy, gitleaks, licence gate | CI `security`, `supply-chain` |
| **DAST** | Every PR | OWASP ZAP baseline against the running API (headers, disclosure, misconfiguration) | CI `dast`; locally `make dast` |
| Red-team exercise | Quarterly | Prompt-injection and abuse scenarios by the team | [red-team.md](red-team.md) |
| **External penetration test** | Before go-live; annually; after major change | Scope below, by an independent firm | This document |

## Choosing the tester

A firm whose testers hold recognised certifications (e.g. CREST, OSCP/OSCE or equivalent), with
experience testing **LLM applications** (prompt injection, tool abuse, data exfiltration through model
output) as well as web/API and cloud. Contract: NDA, rules of engagement below, written authorisation from
the system owner and from AWS-hosted accounts' owners, professional liability insurance.

## Scope

In scope: the API (all routes), the Angular app, OIDC sign-in flow, staging AWS account (ECS, ALB, S3,
SQS, Secrets Manager policies), agent behaviour via data the tester controls (ad-platform sandbox accounts
and knowledge-base uploads), the executor's refusal logic.

Out of scope: the production account; third-party SaaS (AWS, Atlas, PagerDuty) themselves; denial-of-service
volume tests; social engineering of staff.

Environment: **staging**, with two synthetic tenants (`pentest-a`, `pentest-b`), one user per role in each,
synthetic ad data, real models. The executor is pointed at platform **sandbox** accounts only.

## Objectives (what "pass" means)

1. A user or document in tenant A cannot read, infer or influence tenant B's data (including through chat,
   RAG retrieval, reports and error messages).
2. No path moves money without a valid, signed approval by a user with sufficient authority; replay,
   tampering and approval-after-change are refused.
3. Injected instructions in campaign names, documents or chat cannot cause tool use, data exfiltration or
   guardrail bypass beyond being flagged and quarantined.
4. Tokens cannot be forged, replayed across tenants or escalated in role (algorithm confusion, `kid` tricks,
   audience/issuer confusion, stale JWKS).
5. Audit history cannot be altered without the chain check or the write-once archive detecting it.
6. No secret or customer data appears in logs, traces, prompts in the archive, error responses or exports.

## Rules of engagement

Testing window agreed in writing; a named contact on each side; stop and report immediately on a critical
finding or any sign of real customer data; no persistence beyond the window; all test accounts and data
deleted afterwards (`adintel offboard` for the two tenants).

## Deliverables and remediation

Report with CVSS-scored findings, reproduction steps and evidence; executive summary for customers.
Fix times follow [SECURITY.md](../../SECURITY.md): critical 7 days, high 30 days, medium 90 days. Every
fixed finding gets a regression test or eval case. Free retest of critical/high findings. Customers may
request the executive summary under NDA (DPA §8).
