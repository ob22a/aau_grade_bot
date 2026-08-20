# 015. One `AsyncSession` per Unit of Work and Concurrent Task

* **Status:** Accepted
* **Date:** 2026-07-16

## Context

* **The System/Problem:** The application uses SQLAlchemy's `AsyncSession` together with the Unit of Work and Repository patterns. Request handlers, scheduled jobs, and event handlers all perform database operations that may execute concurrently.

* **The Pain Point:** `AsyncSession` is designed to represent a single transactional unit of work and is **not thread-safe or task-safe**. Allowing a session to escape its owning `async with` block, sharing a session across concurrent tasks, or allowing repositories to create and manage their own sessions can lead to invalid transaction state, use of closed connections, unexpected rollbacks, and difficult-to-debug concurrency issues. While connection pool features such as `pool_pre_ping` and `pool_recycle` help recover stale database connections, they do not prevent incorrect session ownership or lifecycle management.

* **The History:** Earlier implementations risked reusing an `AsyncSession` after it had already been closed or committed, particularly when background tasks or concurrent operations shared the same session. This occasionally resulted in errors caused by closed asyncpg connections and blurred ownership of transaction boundaries between repositories and application services.

## Decision

**Each request handler, scheduled worker, background task, and event handler SHALL create its own Unit of Work from a shared session factory. Each Unit of Work SHALL own exactly one `AsyncSession`, explicitly commit successful work, roll back on exceptions, and close the session when the Unit of Work exits. Repositories SHALL receive the session from the Unit of Work and SHALL NOT create, commit, roll back, close, or share sessions. Objects returned from repositories SHALL be detached domain models or DTOs rather than session-managed ORM instances.**

## Alternatives Considered

* **Share a single `AsyncSession` across multiple concurrent tasks:** Rejected. `AsyncSession` is not designed for concurrent use. Sharing it across tasks can corrupt transaction state, produce race conditions, and result in unpredictable failures.

* **Allow repositories to create and manage their own sessions:** Rejected. This fragments transaction boundaries, prevents multiple repository operations from participating in the same transaction, and makes it impossible for the Unit of Work to guarantee atomic commits and rollbacks.

* **Rely on connection pool settings (`pool_pre_ping`, `pool_recycle`) to prevent failures:** Rejected. These settings only protect against stale or dropped database connections. They do not solve incorrect session ownership, improper lifecycle management, or concurrent session usage.

## Consequences & Safety Steps

* **The Trade-off:** Every independent execution context (HTTP request, scheduled job, event handler, or background task) must construct its own Unit of Work from the session factory. This introduces slightly more boilerplate but guarantees well-defined transaction ownership and predictable session lifecycles.

* **Crypto/Code Dangers:**

  * Sharing an `AsyncSession` between concurrent tasks can produce race conditions, transaction corruption, and runtime exceptions.
  * Using an `AsyncSession` after its owning context has exited can result in attempts to use closed database connections.
  * Allowing repositories to call `commit()` or `rollback()` independently breaks transaction atomicity and can leave the application in a partially committed state.
  * Passing ORM instances outside the Unit of Work may expose session-managed objects whose behavior depends on an active session, potentially causing unintended lazy loading or persistence.

* **Open Questions / Future Work:**

  * Standardize dependency injection so every execution context receives a session factory rather than a session instance.
  * Evaluate instrumentation for detecting leaked sessions and long-running transactions during development.
  * Review transaction boundaries as additional background processing and event-driven workflows are introduced to ensure each concurrent task maintains an independent Unit of Work.
