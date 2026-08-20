## 004. All timestamps are timezone-aware

* Status: Accepted
* Date: 2026-07-07

## Context

* The Trap: SQLAlchemy's shorthand Mapped[datetime] defaults to naive DateTime (no timezone).
* The Bug: An early schema draft silently mixed timezone-aware and naive columns.
* The Risk: Python crashes with a TypeError when comparing naive and aware datetimes. This breaks runtime code calculating scan durations (finished_at - started_at) or staleness checks.

## Decision
Every DateTime column must be declared explicitly using mapped_column(DateTime(timezone=True)). Never rely on the default shorthand syntax.
## Alternatives Considered

* Naive timestamps everywhere (implicit UTC): Rejected. Relies purely on human discipline. The existing codebase already proved that this convention is too easy to violate by accident.

## Consequences & Safety Steps

* SQLAlchemy Hardening (Follow-up): To prevent forgetting timezone=True in future models, map it globally on the Base class using:
datetime: Annotated[datetime, mapped_column(DateTime(timezone=True))]
* Database Sync: PostgreSQL stores timestamptz as UTC internally. No extra app-layer conversion logic is needed.
* Python Requirement: App code must pass aware objects only. Use datetime.now(timezone.utc). Avoid datetime.now() and the deprecated, misleading datetime.utcnow().