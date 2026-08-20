# 009. Grade-change baseline is judged against the cohort's own term, not the clock

**Status:** Accepted
**Date:** 2026-07-09

## Context

A `CohortState` row's first-ever scan will surface every course a
representative (or, once section grouping ships, any tracked user) has ever
been enrolled in including courses from long-past semesters. Naively
treating "first time this assessment is seen" as "no grade change, this is
just a baseline" would work for that historical backlog, but it has a real
failure mode: if a genuinely new, currently-releasing grade happens to be
seen for the first time during that same initial scan, blanket-suppressing
all first-sightings would swallow a real event a user actually needed to be
notified about.

The instinctive fix compare the assessment's term against
`datetime.now()` was considered and rejected. Academic year strings
(`"2023/2024"`) span a calendar-year boundary, so a bare `.year` comparison
is wrong for a real portion of the year, and mapping AAU's actual term
boundaries to wall-clock dates requires date-range logic with no clean
formula behind it.

## Decision

An assessment's `(academic_year, semester)` is compared against the
`CohortState` row it's being evaluated under not against wall-clock time.

- If they **don't match**, the assessment belongs to a different term than
  the one actively being tracked. Treated as baseline: recorded, never
  triggers a `GradeChangeStatus` notification, regardless of whether it's
  the first time it's been seen.
- If they **match**, this is the actively-tracked term by construction. A
  populated grade here is a real release event even on the very first
  scan of a brand-new `CohortState` row with nothing to compare against
  yet and should be classified as a change worth notifying about.

## Alternatives considered

- **Blanket-suppress all first-sightings.** Rejected this is exactly the
  failure mode described above: a real release landing on a cohort's first
  scan would be silently missed.
- **Compare against `datetime.now()` / the current calendar date.**
  Rejected academic year strings don't map cleanly onto calendar time,
  and this would need date-range logic with no natural home in the schema,
  for a comparison the schema already has a cleaner answer to.

## Consequences

- This logic depends only on data already present on both records (the
  assessment's term, the `CohortState` row's key) no dependency on the
  `system_settings` current-term pointer from [ADR 010](./010-current-term-pointer.md),
  and it must stay that way. If this logic is ever refactored to read that
  pointer for convenience, a late-updated pointer would reintroduce exactly
  the bug this ADR fixes, just moved to term boundaries.
- Retaking a course in a new term produces a fresh `(academic_year,
  semester)` pair distinct from the original attempt, so a retake's grade
  is correctly treated as a new event under its own term, not conflated
  with the original attempt's grade.