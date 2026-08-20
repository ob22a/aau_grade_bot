# Redis and FSM persistence

Redis is used for short-lived operational state, especially conversation flows and rate-limiting style caches.

## Why Redis is used

- Conversation state is high-churn and ephemeral.
- A TTL-based store is better than a relational table for abandoned dialog flows.
- Cache-aside reads reduce repeat database work.

## What it stores

Planned and scaffolded Redis-backed responsibilities include:

- Telegram FSM state data
- Registration cooldown markers
- Cached grade snapshots
- Distributed locks for cron runs

## FSM design

The project models conversations explicitly:

- `RegistrationFSM`
- `AdminBroadcastFSM`
- `AccountDeletionFSM`
- `SectionFSM`

This keeps handler code readable and makes transitions testable.

## Storage behavior

- FSM state entries should expire automatically.
- Cached grades should expire after a configured period.
- Lock keys should be short-lived and released after work completes.

## Operational caution

Redis outages can affect user flows. Handlers and services should treat cache and FSM storage as helpful infrastructure, not as the only source of truth.

When Redis is unavailable, the application should still protect core flows and fail safely rather than losing persistent business data.
