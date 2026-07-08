# 007. Conversation state is tracked with a formal FSM, persisted in Redis

* **Status:** Accepted
* **Date:** 2026-07-08

## Context
* **The System/Problem:** Multi-step user interactions (e.g., registration flows like ID → password → confirm) are tracked via in-memory Python dictionaries keyed by `telegram_id`.
* **The Pain Point:** In-memory state does not survive application process restarts, which happen frequently on the platform's free tier. Additionally, scattered `if/else` state checks across message handlers become chaotic and error-prone as the application grows.
* **The History:** Temporary variables worked for initial development, but routine process restarts cause the bot to silently freeze mid-flow for active users, ruining the onboarding experience.

## Decision
**Conversation flows will be modeled using an explicit Finite State Machine (FSM) with state persistence moved out of memory and into Redis. State entries will use a Time-To-Live (TTL) to automatically prune abandoned sessions.**

## Alternatives Considered
* **Keep in-memory state and accept the loss:** Rejected. Restarts on the free tier are too frequent, and silent, stuck registration flows create a terrible user experience.
* **Persist state in Postgres instead of Redis:** Rejected. Conversation state is ephemeral, high-churn, and does not need relational durability. Postgres would require extra database migrations and custom cleanup scripts, whereas Redis handles TTL expiration natively.
* **In-memory state with periodic snapshotting:** Rejected. This introduces significant architectural complexity and reconciliation logic for no real performance benefit over using Redis directly.

## Consequences & Safety Steps
* **The Trade-off:** Adding a new flow now requires explicit upfront design work to map out states and valid transitions, rather than just throwing variables into a handler on the fly.
* **Crypto/Code Dangers:** **CRITICAL:** Moving state to an external store means conversation flows are now vulnerable to Redis outages. A Redis timeout or connection failure inside a message handler could crash the worker or trap users in an unresolvable state loop. The existing Redis retry logic must be validated for this use case.
* **Open Questions / Future Work:** The specific FSM implementation mechanism is undecided. The choice remains between migrating the project to a framework with built-in Redis FSM support (like `aiogram`) or writing a lightweight, custom FSM layer on top of the current dispatcher. This will be resolved alongside ADR 008.