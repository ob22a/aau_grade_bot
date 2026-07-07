## 003. Cohort state is split into a live snapshot and an append-only log

* Status: Accepted
* Date: 2026-07-07

## Context

* Dual Needs: The canary scanner needs to know "what is true right now" (current representative, resume points) and "what happened in the past" (for debugging and historical change metrics).
* Data Shapes: Current state is a single row overwritten constantly. History is an immutable, append-only dataset that only grows.

## Decision
Split into two distinct tables:

   1. cohort_states: One row per cohort, updated in place. Natural primary key is (department_id, academic_year, semester).
   2. cohort_scans: Append-only, insert-only log tracking one row per scan attempt, linked to cron_runs.

## Alternatives Considered

* Single Unified Table: Rejected. Finding the "current" state would require an ORDER BY + LIMIT 1 query instead of an instant primary-key lookup. Failed/incomplete scans would also accidentally corrupt historical state reasoning.

## Consequences & Implementation Details

* Double Write Cost: Every scan run must perform two database operations: update the snapshot and insert the log row. This is a standard trade-off for clean audit separation.
* Data Growth: cohort_scans will grow unbounded. This is the only table that will eventually need custom indexing and a long-term retention/pruning policy. cohort_states remains small and fixed-size.
* Idempotency & Constraints: Idempotency is enforced strictly on cohort_scans using a UNIQUE(run_id, department_id, academic_year, semester) constraint to stop duplicate cron jobs from creating double logs. cohort_states stays simple, keyed solely by the cohort itself.