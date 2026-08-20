# 020. Grade Reads Use Cache-Aside Storage with Authoritative Invalidation

* **Status:** Accepted
* **Date:** 2026-07-16

## Context

* **The System/Problem:** Grade retrieval is the application's most common read operation. To reduce database load and improve response times, the application uses Redis as a cache while PostgreSQL remains the system of record.

* **The Pain Point:** Free hosting environments provide limited database resources, making repeated database reads unnecessarily expensive. However, allowing cached data to become the authoritative source risks serving incorrect or outdated grades to users. Cache ownership must therefore be centralized, and cache consistency must be maintained whenever grade data changes.

* **The History:** Earlier designs risked exposing cache management to application services or allowing cache state to diverge from the database. This would increase coupling, duplicate cache logic, and make it more difficult to guarantee that user-visible grades always reflect the authoritative database state.

## Decision

**The grade repository SHALL own all cache interactions using the cache-aside pattern. On grade retrieval, the repository SHALL first attempt to read an encrypted per-user grade snapshot from the cache. On a cache miss, the repository SHALL retrieve the data from PostgreSQL, return the result, and populate the cache. Following every successful grade persistence, the repository SHALL invalidate the affected user's cached grade snapshot before any response is returned or any notification is published. PostgreSQL SHALL remain the authoritative source of truth. Cache failures SHALL degrade gracefully to direct database access without affecting application correctness. Application services SHALL NOT access Redis directly or manage cache keys.**

## Alternatives Considered

* **Allow application services to manage cache reads and invalidation:** Rejected. This duplicates caching logic, spreads Redis knowledge throughout the application layer, and increases the likelihood of inconsistent invalidation.

* **Treat Redis as the primary source of grade data:** Rejected. Cache contents are inherently temporary and may expire, be evicted, or become unavailable. User-visible grades must always be derived from the authoritative database.

* **Update the cache independently after database writes without invalidation:** Rejected. Independent cache updates risk divergence between cached and persisted data if either operation fails or executes out of order.

## Consequences & Safety Steps

* **The Trade-off:** The repository assumes additional responsibility for cache management, including cache lookups, population, and invalidation. Cache misses immediately following invalidation are expected and accepted because they simply fall back to PostgreSQL before repopulating the cache.

* **Crypto/Code Dangers:**

  * Redis MUST NOT be treated as the authoritative source of grade data.
  * Cache invalidation MUST occur only after grade persistence has completed successfully and before any response or notification exposes the updated data.
  * Cache failures MUST NOT prevent grade retrieval or persistence; the application SHALL fall back to PostgreSQL.
  * Application services MUST NOT construct cache keys or interact with Redis directly, ensuring cache ownership remains centralized within the repository.

* **Open Questions / Future Work:**

  * Evaluate cache expiration policies based on production usage patterns.
  * Monitor cache hit rates to determine whether additional grade-related queries would benefit from caching.
  * Review whether cache encryption strategy requires adjustment as cached payloads evolve.
