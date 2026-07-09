# 013. Section self-report fallback, with a trust boundary

**Status:** Accepted
**Date:** 2026-07-09

## Context

`User.section` ([ADR 012](./012-user-section-storage.md)) is populated by
scraping, but section isn't always available on AAU's portal right away
notably at the start of a term. A user in that window has no known section,
and since section now drives cohort sampling
([ADR 011](./011-section-in-cohort-key.md)), an unknown section means that
user falls outside section-level canary coverage until it's resolved.

That gap is time-bounded and low-stakes on its own it closes automatically
the first time a scrape succeeds, and it occurs before grades exist to miss
in the first place, so no notification is actually at risk during it. But
letting a user self-report their section closes the gap sooner and avoids
leaving anyone in an unscanned state for longer than necessary, at the cost
of accepting user-supplied input into a field that now affects sampling
correctness for whoever else shares that section.

## Decision

A user whose section is unknown can be prompted (via a Telegram FSM flow)
to self-report it. Two things bound the risk this introduces:

1. **`User.section_source`** (`SCRAPED` | `USER_REPORTED`) records where the
   current value came from. A scraped value always overwrites a
   self-reported one the moment it becomes available.
2. **A self-reported value can group its owner for their own sampling, but
   never makes them a canary representative for others.** Representative
   selection only ever considers users with `section_source == SCRAPED`
   a wrong or fabricated self-report can only ever affect the one user who
   entered it, never degrade the sampling quality of anyone else's section.

Input is validated (restricted charset, short max length) and, once at
least one real scrape has been observed for a department, checked against
previously-seen section values a non-matching input is flagged, not
blocked outright, since rejecting it risks locking out a legitimately new
or rare section on its first sighting. Any echo of user-supplied text back
into a formatted (`MarkdownV2`/`HTML`) Telegram message is escaped before
sending a general rule this feature is one more instance of, not a
novel risk it introduces on its own.

## Alternatives considered

- **No self-report, leave the user unscanned until a scrape succeeds.**
  Simpler and has zero trust-boundary surface, but leaves users in
  unscanned limbo for longer than necessary for a gap that self-reporting
  can close immediately and safely, given the representative restriction
  below.
- **Allow self-reported users to become representatives.** Rejected this
  is the one alternative that would actually let a bad self-report harm
  someone other than its author. A garbled or fabricated section value
  chosen as a representative would produce a useless probe for real
  students correctly grouped into that (non-existent or wrong) section.

## Consequences

- A user who self-reports a real section they don't actually belong to is
  contained to affecting only their own notifications covered by the
  representative restriction above, and matches how this was reasoned
  through: the blast radius of a wrong-but-real self-report is
  self-limiting by design.
- A user who self-reports a fabricated section becomes a one-person cohort
 not a coverage gap (they're individually checked every cycle, which is
  strictly more thorough than being unassigned), but a standing resource
  cost: one extra scrape per cron cycle, for as long as the fabricated
  value persists. This is bounded by the same overwrite-on-scrape behavior
  from ADR 013 the moment a real scrape succeeds, the fabricated value is
  replaced automatically but isn't bounded by anything if a real scrape
  never succeeds for that user, which validation is meant to reduce the
  likelihood of, not eliminate.
- Registration already requires a real AAU credential to reach the point of
  being scraped at all, which meaningfully limits large-scale abuse of this
  specific input compared to a typical open-signup text field this
  doesn't remove the need for validation, but it does bound how cheap
  abuse actually is.