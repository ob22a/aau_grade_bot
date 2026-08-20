# 011. Section is added to the cohort sampling key

**Status:** Accepted
**Date:** 2026-07-09

## Context

Canary sampling works on a homogeneity assumption: check one representative
user, and if their grades haven't changed, trust that the rest of the
cohort's grades haven't either. That assumption only holds if everyone in
the sampled group actually shares a correlated release schedule.

Within a single `(department, academic_year, semester)` cohort, students
are further split into sections, and different sections can have different
lecturers who release grades on their own independent schedules. That
means the current cohort key groups together several *actually independent*
release schedules as if they were one homogeneous group. Concretely, this
produces two failure modes, both already live risks in the current schema:

- A representative in an early-releasing section triggers a fan-out
  notification to the *entire* department+semester cohort, including
  students in sections that haven't released yet not incorrect, but
  wasteful, and it burns the "change detected" signal on a scan that finds
  nothing new for most of the notified users.
- A representative in a slow-releasing section sees no change, so the scan
  stays quiet while a different, early-releasing section's grades sit
  live and unnoticed, because no representative was ever checked from that
  section.

## Decision

`section` becomes part of the cohort sampling key. `CohortState`'s primary
key extends to `(department_id, academic_year, semester, section)`, and
`CohortScan` gains a `section` column, included in both its unique
constraint and its lookup index.

Section is scoped **within** a department the same section label in two
different departments is unrelated, and even a course cross-listed between
departments is taught as separate sections (almost always with separate
lecturers) per department, not one shared section. `section` is never
meaningful on its own, only combined with `department_id`.

## Alternatives considered

- **Leave sampling at department+term granularity, accept the imprecision.**
  Rejected the two failure modes above are real behavior changes users
  would notice (a late or duplicate-feeling notification), not a
  theoretical edge case, once section-correlated release timing is common
  enough.

## Consequences

- The number of actively-tracked cohorts multiplies by however many
  sections exist per department+term, which directly multiplies scan
  volume this is the acknowledged cost of the correctness fix, and worth
  watching against the project's existing ~150–200 user scaling ceiling on
  free-tier infrastructure.
- Grouping by section depends on `User.section` being known see
  [ADR 012](./012-user-section-storage.md) for how that value is captured,
  and [ADR 013](./013-section-self-report-fallback.md) for how users with
  an unknown section are handled without silently breaking sampling
  coverage.