# Threat model

This project stores credentials and academic records, so the threat model is intentionally conservative.

## Sensitive assets

- Telegram bot token
- AAU portal username and password
- Stored grade details
- Stored assessment details
- Cron secret and admin secrets
- Audit log events and operational metadata

## Main threats

- Database compromise exposing credentials or grade records
- Portal HTML layout changes breaking scrapers
- Credential reuse or lockout caused by aggressive retries
- Telegram command abuse by unauthorized users
- Sensitive data leakage through logs or fixtures
- Stale async database connections causing failed operations during runtime

## Defensive choices

- Encrypt credentials and grade payloads at rest with AES-256-GCM
- Validate portal IDs locally before portal access
- Classify credential failures conservatively and avoid automatic retries
- Keep handlers thin and push logic into services
- Use typed diagnostics that avoid leaking raw HTML or personal data
- Scope every async session to one Unit of Work
- Add rate limits, a portal semaphore, and cron locking

## What is not protected by design

- The AAU portal itself remains the source of truth
- Redis is treated as operational state, not durable business storage
- Python cannot guarantee in-memory zeroization after secrets are used

## Admin response expectations

- The first schema change should alert admins immediately
- Repeated schema failures should be deduplicated and aggregated
- Portal lockout risk should force a protective cooldown before another login attempt
- Destructive lifecycle actions should require confirmation and be audit-logged
