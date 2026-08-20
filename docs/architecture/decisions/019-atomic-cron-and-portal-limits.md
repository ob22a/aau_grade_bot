# 019. Cron Is Authenticated, Atomic, and Portal-Concurrency Limited

* **Status:** Accepted
* **Date:** 2026-07-16

## Context

* **The System/Problem:** The application periodically executes scheduled work through a cron endpoint to probe the AAU portal, detect updates, and perform related background processing. The application may be deployed on hosting platforms where scheduled requests can be retried or multiple application instances may briefly execute simultaneously.

* **The Pain Point:** Without coordination, overlapping cron executions may perform duplicate work, repeatedly authenticate against the AAU portal, generate duplicate notifications, or process the same users concurrently. Additionally, unrestricted parallel portal access can place unnecessary load on the external system. Cron execution must therefore be coordinated across all running application instances while limiting concurrent portal access.

* **The History:** Earlier execution assumed only a single cron process would be active at any given time. This assumption is not guaranteed in distributed or hosted environments, where retries, overlapping deployments, or multiple application instances may result in concurrent cron execution.

## Decision

**The `POST /cron` endpoint SHALL require authentication using the `X-Cron-Secret` request header. Before performing scheduled work, the application SHALL acquire a distributed lock covering the entire cron execution. If another execution already owns the lock, the endpoint SHALL return successfully without performing any work. Portal authentication and requests SHALL be limited using a configurable semaphore, initially permitting three concurrent portal sessions. Scheduled work SHALL prioritize cohorts by their oldest recorded probe time and SHALL resume progress using persisted state. Scheduled portal scans SHALL NOT execute between 00:00 and 07:00 East Africa Time (EAT).**

## Alternatives Considered

* **Allow overlapping cron executions:** Rejected. Concurrent executions can duplicate work, increase unnecessary portal logins, and generate duplicate notifications or inconsistent processing.

* **Rely solely on the hosting platform to prevent concurrent execution:** Rejected. Hosted environments may retry requests, restart applications, or temporarily run multiple instances. Application-level coordination is required to guarantee a single active cron execution.

* **Allow unrestricted concurrent portal access:** Rejected. Excessive parallel logins increase load on the AAU portal and may reduce application stability or trigger rate limiting.

## Consequences & Safety Steps

* **The Trade-off:** Scheduled work may occasionally be skipped when another execution already holds the distributed lock. Portal throughput is intentionally limited by the configured semaphore to prioritize stability over maximum parallelism.

* **Crypto/Code Dangers:**

  * The `X-Cron-Secret` MUST be validated before any scheduled work begins.
  * The distributed lock MUST be stored in a shared, durable coordination mechanism so that all application instances observe the same lock state.
  * The lock MUST always be released correctly, including when exceptions occur, to prevent stale locks from blocking future executions.
  * Portal concurrency MUST remain bounded by the configured semaphore to avoid excessive simultaneous logins.
  * Persisted progress MUST be updated consistently so interrupted executions can resume without unnecessarily repeating completed work.

* **Open Questions / Future Work:**

  * Review the configured semaphore size as operational experience with portal capacity is gathered.
  * Evaluate lock expiration and recovery strategies for unexpected process termination.
  * Monitor probe scheduling to determine whether prioritization or scheduling windows should be adjusted as usage patterns evolve.
