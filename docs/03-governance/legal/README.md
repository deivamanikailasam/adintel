# Legal and privacy pack

The owner's decisions on data protection and AI transparency, written so that a customer's procurement,
privacy and security reviewers can answer their questionnaires from them. **Templates are a starting
point, not legal advice: have counsel review them for each jurisdiction before signature.**

| Document | Purpose | Decision recorded |
|----------|---------|-------------------|
| [Data processing agreement (template)](dpa-template.md) | Contract terms between the vendor and each agency | Vendor is a processor; agency is controller |
| [Sub-processor register](subprocessors.md) | Who else touches customer data, where, why | Local: none. Production: AWS, MongoDB Atlas only for customer data |
| [Records of processing](records-of-processing.md) | GDPR Art. 30 register | Five processing activities, purposes, lawful bases, retention |
| [Data protection impact assessment](dpia.md) | Risk assessment of the AI processing | Residual risk low; no solely automated decisions about people |
| [AI system card](ai-system-card.md) | Intended use, limits, oversight, evaluation | Human-in-the-loop (L2) is a design invariant |
| [ADR L-15](../../02-decisions/l-15-model-provider-data-terms.md) | Which model providers may receive data | No training, zero retention, enforced in code |
