# 006. Health check returns 204, not 200

* **Status:** Accepted
* **Date:** 2026-07-07

## Context
* **The System/Problem:** The application's only HTTP surface (`main.py`) exists solely for an external uptime monitor and the hosting platform to verify that the background process is still alive.
* **The Pain Point:** The endpoint is polled continuously at a fixed interval indefinitely. Returning a standard response body serializes and transfers unnecessary bytes over the wire.
* **The History:** On resource-constrained free-tier hosting, minimizing overhead is essential since the uptime monitor only cares about request success, not a descriptive payload.

## Decision
**The health check endpoints (`/` and `/health`) respond with HTTP 204 No Content instead of the conventional 200 OK with a `{"status": "ok"}` JSON body.**

```python
async def handle_health_check(request):
    return web.Response(status=204)  # No content — avoids unnecessary data transfer

```

## Alternatives Considered

* **200 OK with a JSON body:** Rejected. While more self-describing for a human using `curl`, the JSON body carries no information that a bare status code doesn't already convey. A 204 response also drops the `Content-Type` header, stripping down the response size even further.

## Consequences & Safety Steps

* **The Trade-off:** Manual debugging via `curl -i` returns a blank body, which might mimic a broken endpoint to someone caught off guard. This requires a small code comment or documentation note.
* **Crypto/Code Dangers:** **CRITICAL:** A `204` status code only indicates "process is alive." If the endpoint needs to report internal system health (e.g., a connection pool exhaustion or database failure), it will silently mask these runtime failures as healthy.
* **Open Questions / Future Work:** If the bot requires deeper diagnostic capabilities down the road, this decision must be revisited to handle fine-grained error reporting.