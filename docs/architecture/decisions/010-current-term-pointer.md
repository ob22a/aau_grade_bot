# 010. A `system_settings` pointer tracks the current term, for scheduling only

**Status:** Accepted
**Date:** 2026-07-09

## Context

Once a term ends, its cohorts stop producing new grades but nothing in
the schema currently tells the scheduler that. Without a way to know which
`(department, academic_year, semester)` combinations are "live," the
scheduler either has to derive it from wall-clock time (rejected in
[ADR 009](./009-baseline-grade-classification.md) for the same reasons:
academic year strings don't map cleanly to calendar dates) or keep probing
every cohort that has ever existed, forever.

## Decision

Two `system_settings` keys `current_academic_year` and
`current_semester` hold the currently-active term. These are updated
explicitly, either by a scheduled job or an admin action, at the actual
term transition. This is **not** a database trigger: nothing in this
schema changes on a calendar date, so there's no row event for a trigger
to fire on the update has to be an explicit, deliberate write, timed by
whoever (or whatever job) knows the real transition date.

The scheduler uses this pointer to decide which cohorts are worth actively
probing. It is explicitly **not** used anywhere in grade-change
classification that decision is made per-record against each
`CohortState` row's own key, independent of this pointer, per
[ADR 009](./009-baseline-grade-classification.md).

## Alternatives considered

- **Derive "current term" from wall-clock time.** Rejected for the same
  reason as in ADR 009 no clean formula maps a calendar date to AAU's
  actual term boundaries.
- **Let the pointer also gate grade-change classification**, instead of
  keeping two separate mechanisms. Rejected deliberately: if this pointer
  is updated even slightly late (registrar delays, a missed cron run), a
  correctness-critical read of it would recreate the exact
  first-scan-swallows-a-real-grade bug ADR 009 exists to prevent just
  relocated to term boundaries instead of eliminated. Keeping this pointer
  scoped to scheduling only means it being stale has a bounded, low-stakes
  cost (a wasted scan, or a slightly-late skip) instead of a correctness
  failure.

## Consequences

- This pointer can be wrong at the boundary (updated a few days early or
  late) without ever causing a missed or duplicate notification worst
  case is one extra scan cycle spent on a cohort that's actually done, or
  one cohort skipped a cycle late. That bounded blast radius is the entire
  point of scoping this to scheduling only.
- Whatever job or command updates this pointer needs to be triggered by a
  real decision (an admin flipping it, or a scheduled task with the actual
  term calendar baked in) there's no way to make this self-updating from
  data already in the system, since the system has no signal for "a new
  term has started" other than this pointer itself.