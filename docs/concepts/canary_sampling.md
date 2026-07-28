# Canary Sampling

Canary sampling is the scheduler strategy used to detect grade releases while minimizing unnecessary traffic to the AAU portal.

Rather than scraping every student on every scheduled run, the scheduler monitors one representative ("canary") from each cohort. Because students in the same cohort typically receive grades at approximately the same time, detecting a grade change for a representative indicates that the rest of the cohort should be checked.

The goal is to reduce portal load while still detecting grade releases quickly and safely.

---

# Why Canary Sampling Exists

The AAU portal is an external system with finite capacity, and the application frequently runs on resource-constrained hosting.

Scraping every registered student during every cron cycle would:

* generate unnecessary portal logins,
* increase scheduler runtime,
* consume more database and network resources,
* increase the likelihood of portal throttling or account lockout.

Instead, the scheduler performs a lightweight probe using a representative student for each cohort.

If the representative's grades have not changed, the remaining students in that cohort are skipped because a widespread release is unlikely.

If a grade change is detected, the scheduler performs a full scan of that cohort to determine exactly which students received new or updated grades.

---

# Cohort Definition

A cohort represents students who are expected to receive grade updates together.

A cohort is uniquely identified by:

* Department
* Academic Year
* Semester
* Section

The database enforces this identity through the composite primary key of `cohort_states` and the corresponding cohort fields in `cohort_scans`.

Section is intentionally included because students from the same department and academic year may belong to different teaching sections whose grades are released independently.

For example:

```text
Software Engineering
2023/2024
Second Semester
Section A
```

and

```text
Software Engineering
2023/2024
Second Semester
Section B
```

are treated as separate cohorts.

---

# Representative Selection

Each cohort has one representative user.

The representative is stored in `cohort_states.representative_user_id`.

The representative serves as the first portal probe during scheduled execution.

The scheduler does not assume the representative is permanent.

If the representative:

* loses valid credentials,
* becomes unavailable,
* triggers the credential policy described in ADR 021,

the scheduler selects another eligible user from the same cohort.

This prevents a single account from blocking future monitoring.

---

# Scheduler State

Canary sampling separates **current scheduler state** from **historical execution records**.

## `cohort_states`

`cohort_states` stores the current state of every cohort.

Examples include:

* current representative,
* last successful probe,
* last detected grade change,
* current scan status,
* resume position,
* progress counters.

This table represents the scheduler's current view of each cohort and is updated as work progresses.

---

## `cohort_scans`

`cohort_scans` records every scan attempt performed by every cron run.

Each record captures information such as:

* the cron run,
* the cohort,
* representative used,
* scan status,
* grade-change outcome,
* timestamps,
* progress.

Unlike `cohort_states`, this table is append-only and serves as the historical audit trail of scheduler activity.

---

# Scan Flow

A scheduled execution proceeds as follows:

1. Cron acquires the distributed scheduler lock.
2. Cohorts are ordered by their oldest recorded probe time.
3. The representative for the next cohort is scraped.
4. Parsed grades are compared against the persisted grades.
5. One of two outcomes occurs.

### No grade change

If no change is detected:

* the cohort's probe time is updated,
* the scan is recorded,
* the scheduler proceeds to the next cohort.

No additional users are scraped.

---

### Grade change detected

If a representative's grades have changed:

* the cohort state records the detected change,
* the scheduler begins scanning the remaining students in that cohort,
* every student's grades are parsed and compared individually,
* notifications are generated only for students whose grades actually changed.

This ensures that a representative merely signals **when** a cohort should be scanned—it does not determine which students receive notifications.

---

# Parsing During a Scan

Every portal response is parsed according to the parser rules defined by the application.

Parser outcomes fall into two categories:

### Recoverable variations

Minor HTML differences produce warnings while still returning valid parsed data.

Scanning continues normally.

---

### Correctness-critical failures

If required grade information cannot be parsed safely, the parser raises a typed failure rather than producing speculative grade data.

In this situation:

* the affected scan is treated as failed,
* administrators are alerted,
* the scheduler never guesses whether grades changed.

This behavior preserves correctness even if the AAU portal changes unexpectedly.

---

# Manual Scrapes

Users may manually request a grade refresh.

A successful manual scrape updates the authoritative database before the scheduler executes.

When the scheduler later reaches that cohort, it may determine that the representative has already been checked recently and skip an unnecessary portal probe.

This avoids redundant work while keeping scheduled execution consistent.

---

# Interrupted Runs

A scheduler run may terminate before every user in a cohort has been processed.

To support recovery, `cohort_states` stores:

* the current scan status,
* the last cron run,
* the resume position,
* progress counters.

These values allow the scheduler to resume work from the last known position rather than restarting the entire cohort scan.

---

# Notification Flow

Notifications are driven by **actual grade differences**, not merely by the representative detecting a change.

The representative only determines whether a full cohort scan is necessary.

Each student's newly parsed grades are compared with the encrypted grades stored in PostgreSQL.

Only students whose persisted grades differ receive notifications.

This prevents unnecessary notifications while ensuring every affected student is informed.

Notification handlers are expected to remain idempotent so repeated scheduler executions or retries cannot produce duplicate notifications.

---

# Relationship to the Overall Architecture

Canary sampling follows the same architectural boundaries used throughout the project:

* The scheduler decides **which cohort to inspect**.
* The portal adapter retrieves HTML from the AAU portal.
* Parsers convert HTML into validated parsed data.
* Repositories persist and retrieve authoritative grade data.
* Cache invalidation occurs after successful persistence.
* Domain events publish notification work.
* Background handlers deliver notifications independently.

Each component owns a single responsibility, allowing the scheduler to coordinate the overall workflow without containing parsing, persistence, caching, or notification logic itself.
