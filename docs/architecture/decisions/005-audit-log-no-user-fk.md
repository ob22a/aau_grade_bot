# 005. Audit logs are not foreign-keyed to users

*   **Status:** Accepted
*   **Date:** 2026-07-08

## Context
*   **The System/Problem:** AuditLog records telegram_id and an action for security- and debugging-relevant events.
*   **The Pain Point:** If a user deletes their account, a standard foreign key constraint would either delete their audit logs (`CASCADE`), destroying the history, or block the deletion entirely.
*   **The History:** Every other table uses standard foreign keys to users.id, but audit trails require decoupled persistence.

## Decision
**AuditLog.telegram_id is a plain indexed integer column, not a foreign key to users.id. Audit rows are written independently of whether the referenced user still exists.**

## Alternatives Considered
*   **FK with ondelete="CASCADE":** Rejected. This deletes the audit trail exactly when a user leaves the system, defeating the purpose of an audit log.
*   **FK with ondelete="SET NULL":** Rejected. Keeping a nullable user_id alongside telegram_id is not adopted for the current schema, though it could be reconsidered if live queries require joins later.

## Consequences & Safety Steps
*   **The Trade-off:** Querying a user's audit history requires a direct telegram_id match instead of an ORM join or relationship.
*   **Crypto/Code Dangers:** **CRITICAL:** Telegram ID reuse is a latent risk. While Telegram does not currently reissue IDs, if that changes, old logs could mistakenly appear associated with a new user using the same ID.
*   **Open Questions / Future Work:** This table will eventually need an independent data retention and archival policy to prune old rows without relying on user deletion logic.