# Data processing agreement — template

> Template for the agreement between **[Vendor]** ("Processor", operator of AdIntel) and **[Agency]**
> ("Controller"). Square brackets are to be completed. Counsel review required before use.

## 1. Subject matter and roles

1.1 The Processor provides AdIntel, which analyses the Controller's paid-advertising performance data,
drafts reports and proposes changes that the Controller's named staff approve or reject.
1.2 For personal data of the Controller's **staff** (user accounts, approvals, chat sessions) and any
personal data contained in **advertising data or uploaded documents**, the Controller is the controller
and the Processor processes it only on the Controller's documented instructions (this agreement, the
Customer Agreement and the Controller's configuration of AdIntel).
1.3 Where the Controller acts for its own clients (the advertisers), the Controller warrants it has the
authority to engage the Processor as a sub-processor and passes down equivalent terms.

## 2. Nature, purpose and data

| | |
|-|-|
| Purpose | Performance monitoring, anomaly investigation, report drafting, recommendation workflow, audit |
| Categories of data subjects | Controller staff; incidentally, persons named in uploaded documents or campaign names |
| Categories of personal data | Name, work email, role, approval and rejection decisions, free-text notes, chat messages, IP/user-agent in access logs |
| Special categories | None intended. The Controller must not upload special-category data; PII detected in model inputs is redacted |
| Duration | Term of the Customer Agreement plus the return/deletion period in §9 |

## 3. Processor obligations

The Processor shall: process only on documented instructions; ensure personnel are bound by
confidentiality; implement the measures in Annex 2; assist with data-subject requests (AdIntel provides
export and erasure — `docs/04-security/privacy-and-data-lifecycle.md`); assist with DPIAs and prior
consultations; notify personal data breaches **without undue delay and within 48 hours** of becoming aware;
make available the information needed to demonstrate compliance and allow audits (§8).

## 4. AI-specific commitments

4.1 Controller data is **never used to train or fine-tune models made available to anyone else**. Brand
voice adapters trained on a Controller's approved reports are used only for that Controller and deleted on
termination.
4.2 Model providers receive data only under terms with **no training and zero retention** (ADR L-15),
enforced by AdIntel's model registry at start-up.
4.3 No change to a Controller's advertising accounts is made without the approval of a named Controller
user with sufficient authority; every action is recorded in a tamper-evident audit log.
4.4 The Processor discloses the models in use and changes to them (the model registry) on request and
gives [30] days' notice of a change of model provider.

## 5. Sub-processors

General authorisation for the sub-processors in the [register](subprocessors.md). The Processor gives
[30] days' notice of additions or replacements; the Controller may object on reasonable data-protection
grounds, in which case the parties discuss alternatives in good faith and the Controller may terminate the
affected service.

## 6. International transfers

Customer data is hosted in **[region, e.g. AWS eu-west-1 / us-east-1]**. Transfers outside it rely on
[Standard Contractual Clauses / the applicable adequacy decision], with a transfer impact assessment on file.

## 7. Security

Annex 2 (technical and organisational measures) — maintained in `docs/04-security/security.md`,
`docs/04-security/tenant-isolation.md` and `docs/10-audit/audit-and-reproducibility.md`.

## 8. Audits

Annually, the Processor provides its latest independent assessment ([SOC 2 Type II / ISO 27001 report, or
penetration-test summary]) and answers a reasonable security questionnaire. On-site audits: once a year on
[30] days' notice, at the Controller's cost, unless after a breach.

## 9. Return and deletion

On termination the Processor exports the Controller's data as a verifiable bundle (JSONL + SHA-256
manifest) within [14] days and then deletes it (`adintel offboard`), except records the Processor must keep
by law (approvals, executions, audit log: up to 7 years) which remain isolated, access-restricted and are
deleted at the end of their retention period. Deletion is confirmed in writing with the audit reference.

## Annex 1 — Processing details: see §2 and the [records of processing](records-of-processing.md).
## Annex 2 — Technical and organisational measures: see §7.
## Annex 3 — Sub-processors: see the [register](subprocessors.md).
