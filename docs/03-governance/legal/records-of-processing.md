# Records of processing activities (GDPR Art. 30(2), processor)

| # | Activity | Data subjects | Personal data | Purpose | Lawful basis (controller's) | Retention | Recipients | Security |
|---|----------|---------------|---------------|---------|-----------------------------|-----------|------------|----------|
| 1 | User accounts and sign-in | Agency staff | Name, work email, roles, approval limit, sign-in events | Access control, approval authority | Contract / legitimate interest | Account lifetime; erasure on request (pseudonymised) | Tenant admins | OIDC/MFA, least-privilege roles |
| 2 | Approval workflow | Agency staff | User id, decisions, typed exposure, notes | Human oversight of spending; accountability | Legal obligation / legitimate interest | Approvals & executions 7 years; notes blanked on erasure | Tenant users in scope, auditors | Signed approvals, hash-chained audit |
| 3 | Performance analysis and reports | Incidental (names in campaign titles or documents) | As contained in advertising data | Analytics, report drafting | Contract (advertiser ↔ agency) | Metrics 25 months, reports 24 months | Tenant users in brand scope | Tenant isolation, PII redaction before models |
| 4 | Conversational assistant | Agency staff | Questions and answers | Answer questions about performance | Legitimate interest | 90 days | The user, tenant admins | As above |
| 5 | Audit, security and operations | Agency staff | User ids in audit entries, access logs | Security, fraud prevention, compliance | Legal obligation / legitimate interest | Audit 7 years; logs 13 months | Admins, auditors, on-call engineers | Write-once archive, access logging |

Processor: [Vendor legal name, address, DPO contact]. Controllers: each agency (Customer Agreement).
Transfers: see the [sub-processor register](subprocessors.md). Technical measures: DPA Annex 2.
Retention is enforced by `adintel purge` from `storage/collections.py` (see the
[data lifecycle](../../04-security/privacy-and-data-lifecycle.md)).
