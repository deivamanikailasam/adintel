# Changelog

Every change to AdIntel is recorded twice:

1. **Here**, as a one-line summary per step, newest last.
2. **In [`docs/changelog/`](docs/changelog/)**, as a short plain-English note that explains
   *what changed, why it matters and what it means for someone who is not an engineer*.

The two always move together: a commit that changes behaviour adds a line here and a note there.

| Step | Change | Plain-English note |
|------|--------|--------------------|
| 0001 | Project foundation: packaging, tooling, conventions | [0001](docs/changelog/0001-project-foundation.md) |
| 0002 | Architecture, system design and decision records | [0002](docs/changelog/0002-architecture-and-decisions.md) |
| 0003 | Core building blocks, configuration and the domain model (RunState) | [0003](docs/changelog/0003-core-config-domain.md) |
| 0004 | Storage layer with tenant isolation built in (memory + MongoDB backends) | [0004](docs/changelog/0004-storage-and-tenant-isolation.md) |
| 0005 | Immutable hash-chained audit log with tamper detection | [0005](docs/changelog/0005-audit-log.md) |
