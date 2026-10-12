# Security policy

AdIntel can move client advertising money (always behind a named human's approval) and holds several
agencies' data side by side. Security reports are taken seriously and handled privately.

## Reporting a vulnerability

- **Do not open a public issue.** Use GitHub's *Report a vulnerability* (Security → Advisories) on this
  repository, or email the maintainer listed in `.github/CODEOWNERS`.
- Include: what you found, how to reproduce it (a failing test is ideal), and the impact you believe it has.
- We acknowledge within **2 business days**, give an initial assessment within **5 business days**, and
  aim to fix critical issues within **7 days** and high within **30 days**. You will be told when the fix ships.

## What we most want to hear about

| Area | Examples |
|------|----------|
| Tenant isolation | Any way for one agency's user, prompt or document to read or influence another agency's data |
| Approval bypass | A change reaching an ad platform without a valid signed approval, or above the approver's limit |
| Executor integrity | Any path that gives the executor model access, or gives the agent worker write credentials |
| Prompt injection | Data from an ad platform or document that makes an agent act on instructions (beyond being flagged) |
| Audit tampering | Altering or deleting audit history without the chain check or the write-once archive noticing |
| Authentication | Token forgery, algorithm confusion, role escalation through the identity provider |
| Secrets | Credentials in logs, prompts, traces, exports or error messages |

Threats already analysed are listed in [docs/04-security/threat-model.md](docs/04-security/threat-model.md);
a report that breaks one of the listed controls is especially valuable.

## Out of scope

The local development defaults (`adintel-local` passwords, the dev JWT secret, the password-less dev login)
are intentionally weak and refused at startup outside `ADINTEL_ENV=local|test`. Reports that only apply to
those defaults are out of scope unless they work with `ADINTEL_ENV=staging|production`.

## Safe harbour

Good-faith research that respects these rules — no access to data that is not yours, no degradation of
service, no social engineering, prompt disclosure to us — will not be pursued.

## Supported versions

Only the latest commit on the default branch receives security fixes.
