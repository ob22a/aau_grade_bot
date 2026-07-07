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