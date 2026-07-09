# 012. `User.section` is a flat column, re-scraped on every cycle

**Status:** Accepted
**Date:** 2026-07-09

## Context

Once section becomes part of the cohort sampling key
([ADR 011](./011-section-in-cohort-key.md)), each user's section needs to
be known somewhere. Section is a term-scoped concept in principle (a
student's section this term isn't guaranteed to be their section next
term), which would normally argue for storing it somewhere term-scoped
(`UserCourse`, or a dedicated table) rather than as a flat field on `User`.

In practice, though: a student's section is stable for the duration of a
term, and typically stable across many terms the only time it usually
changes is retaking a course in a different term/section than the original
attempt. Historical section data ("what section was I in last year") isn't
a hard requirement for anything the bot currently does.

## Decision

`section` is stored as a plain, nullable column on `User`, overwritten with
the latest value on every successful scrape not captured once, not
duplicated per-`UserCourse`, not tracked in a dedicated history table.

## Alternatives considered

- **Store on `UserCourse`,** term-scoped correctly and populated at the
  same time enrollment is scraped. Rejected: since section is uniform
  across a student's whole course load in a given term, this would store
  the identical value on every one of that student's `UserCourse` rows for
  the term a normalization smell that buys correctness the flat-column
  approach doesn't actually lack, given section's real-world stability.
- **A dedicated `(user_id, academic_year, semester) -> section` table.**
  The fully normalized option, and the right shape if the project expects
  to need other early-available, term-scoped-but-not-final attributes
  later. Not adopted now since historical section tracking was confirmed
  as a nice-to-have, not a requirement this is worth revisiting only if
  a second term-scoped-but-needed-early attribute actually materializes.

## Consequences

- Because the value is silently overwritten on every scrape, nothing
  distinguishes "a real section transfer happened" from "the previous
  value was simply wrong" a scraper bug that misparses section would
  quietly and permanently replace a correct value with an incorrect one,
  with no built-in signal that anything changed.
- To offset that blind spot cheaply: every scrape that detects a section
  value differing from what's currently stored logs an `AuditLog` entry
  (`action="section_changed"`, `details={"from": ..., "to": ...}`) before
  overwriting. This gives a rough change history for free, using a table
  that already exists, without committing to a dedicated schema for
  something not currently required.
- If historical section ever does become a hard requirement later, this
  decision would need revisiting in favor of the dedicated-table
  alternative above the `AuditLog` trail softens, but doesn't fully
  replace, that gap.