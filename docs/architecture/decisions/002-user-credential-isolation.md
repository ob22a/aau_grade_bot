## 002. Credentials live in a separate table from users

* Status: Accepted
* Date: 2026-07-07

## Context

* Access Patterns: User (Telegram ID, department) is read constantly everywhere. Credentials (encrypted_password, iv) are only read by the scraper during login.
* Risk: Keeping them together means general queries pull crypto material into memory, risking accidental leaks in logs or debugging output.

## Decision
Store credentials in a dedicated user_credentials table with a 1-to-1 relationship via user_id. Do not mix them into the main users table.

## Alternatives Considered

* Columns on User directly: Rejected. Simpler to query, but brings too much risk of exposing encrypted credentials during basic user lookups.

## Consequences & Security Steps

* Intentional Friction: Code paths must explicitly query or join UserCredential. This makes credential access visible and conscious in the codebase.
* Independent Tracking: Password rotation (updated_at) is isolated from general user activity (User.last_used).
* Safe Destruction: To prevent sensitive data from lingering in database snapshots/backups, application logic must overwrite credentials with random bytes and commit before triggering a cascade delete.