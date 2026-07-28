# Architecture Decision Records

Each file here documents one atomic architectural decision: the problem, the
options considered, what was chosen, and what it costs. New decisions get the
next number in sequence and are never renumbered, even if later superseded —
a superseded ADR stays in place with its status updated, so the history of
*why* the system looks the way it does stays intact.

Use [TEMPLATE.md](./TEMPLATE.md) for new entries.

| # | Title | Status |
|---|-------|--------|
| 001 | [Grades are encrypted at rest, using AES-256-GCM](./001-encrypt-grades-then-gcm.md) | Accepted |
| 002 | [Credentials live in a separate table from `users`](./002-user-credential-isolation.md) | Accepted |
| 003 | [Cohort state is split into a live snapshot and an append-only log](./003-cohort-state-vs-scan-split.md) | Accepted |
| 004 | [All timestamps are timezone-aware](./004-timezone-aware-timestamps.md) | Accepted |
| 005 | [Audit logs are not foreign-keyed to `users`](./005-audit-log-no-user-fk.md) | Accepted |
| 006 | [Health check returns 204, not 200](./006-health-check-204.md) | Accepted |
| 007 | [Conversation state is tracked with a formal FSM, persisted in Redis](./007-fsm-conversation-state.md) | Accepted |
| 008 | [Handlers, services, and repositories are separated, with manual dependency injection](./008-service-repository-di-layering.md) | Accepted |
| 009 | [Grade-change baseline is judged against the cohort's own term, not the clock](./009-baseline-grade-classification.md) | Accepted |
| 010 | [A system_settings pointer tracks the current term, for scheduling only](./010-current-term-pointer.md) | Accepted |
| 011 | [Section is added to the cohort sampling key](./011-section-in-cohort-key.md) | Accepted |
| 012 | [User.section is a flat column, re-scraped on every cycle](./012-user-section-storage.md) | Accepted |
| 013 | [Section self-report fallback, with a trust boundary](./013-section-self-report-fallback.md) | Accepted |
| 014 | [Repositories return domain data, never ORM instances](./014-domain-boundaries-and-repository-results.md) | Accepted |
| 015 | [One AsyncSession per Unit of Work and concurrent task](./015-unit-of-work-and-async-session-ownership.md) | Accepted |
| 016 | [Background work is dispatched through supervised domain events](./016-supervised-domain-events.md) | Accepted |