# 016. Background Work Is Dispatched Through Supervised Domain Events

* **Status:** Accepted
* **Date:** 2026-07-16

## Context

* **The System/Problem:** The application performs operations whose primary business action often produces secondary effects such as scraping, auditing, sending notifications, cache invalidation, metrics collection, or other background processing.

* **The Pain Point:** Directly creating background tasks using `asyncio.create_task()` from application services makes ownership of those tasks unclear. Fire-and-forget tasks may fail silently, lose exceptions, continue running during application shutdown, execute without correlation or tracing information, or become difficult to retry and monitor. This spreads infrastructure concerns throughout the application layer and makes the lifecycle of background work inconsistent.

* **The History:** Earlier implementations launched asynchronous work directly from services whenever a side effect was required. This tightly coupled business logic to task scheduling, complicated error handling, and made it difficult to supervise, observe, and recover failed background operations.

## Decision

**Application services SHALL publish typed domain events instead of directly creating background tasks. A dedicated event dispatcher SHALL own event handler execution, logging, correlation identifiers, retry policies, cancellation, and graceful shutdown. Application services SHALL NOT call `asyncio.create_task()` directly. Event handlers SHALL execute independently using their own Unit of Work and `AsyncSession` when database access is required.**

## Alternatives Considered

* **Launch background work using `asyncio.create_task()` directly from services:** Rejected. This couples business logic to asynchronous execution, makes task ownership unclear, and risks unobserved exceptions, inconsistent shutdown behavior, and missing retry policies.

* **Execute all side effects synchronously before returning:** Rejected. This unnecessarily increases request latency and forces users to wait for operations that are independent of the primary business action, such as notifications or auditing.

* **Allow each service to implement its own retry and logging behavior:** Rejected. This duplicates infrastructure concerns, produces inconsistent behavior across services, and makes operational monitoring more difficult.

## Consequences & Safety Steps

* **The Trade-off:** Introducing a domain event dispatcher adds architectural complexity and requires defining event types, handlers, and dispatch infrastructure. Event handlers must also be designed to operate independently from the originating request.

* **Crypto/Code Dangers:**

  * Event handlers may execute more than once because of retries. Handlers MUST therefore be idempotent so repeated execution does not corrupt data or produce duplicate side effects.
  * Event handlers MUST NOT reuse the originating request's `AsyncSession` or Unit of Work. Each handler is responsible for creating its own Unit of Work when database access is required.
  * Exceptions thrown by handlers MUST be captured, logged, and reported by the dispatcher rather than silently disappearing in unmanaged background tasks.
  * Only work that is independently recoverable should be dispatched asynchronously. Business-critical operations required for the success of the original command MUST remain part of the original transaction.

* **Open Questions / Future Work:**

  * Evaluate replacing the in-process dispatcher with a durable message broker (e.g., RabbitMQ, Kafka, or Redis Streams) if background workload grows beyond a single application instance.
  * Standardize event naming, versioning, and payload structure across the application.
  * Define monitoring dashboards and alerting for failed or repeatedly retried event handlers.
