# Use cases

## V1 scope

1. Register through a persisted Telegram FSM: validate portal ID, collect a password, log in once, encrypt and store credentials, and assign profile data. A failed login is never automatically retried.
2. View cached stored grades on demand. A manual portal scrape is rate-limited to once per user per 30 minutes.
3. Run an authenticated cron endpoint that selects the cohort least recently scanned, resumes interrupted work, detects changes, and notifies affected students.
4. Allow administrators to broadcast, change documented runtime settings with confirmation, inspect metrics, and receive parser/scrape failure alerts.
5. Let a user inspect account activity and request account deletion. Accounts inactive for nine months receive notice before a queued deletion workflow.

## Deliberately deferred

- A web dashboard and non-Telegram notification channels.
- Encryption-key rotation (the cipher interface will support adding it).
- Multi-university portals beyond the AAU adapter.

## Operating rules

- No scheduled portal scrape runs from 00:00 through 07:00 Africa/Nairobi.
- A successful manual scrape may satisfy the cohort's next scheduled probe; when it detects a change, affected classmates are updated/notified.
- Parser failures retain successfully parsed fields as warnings where safe, raise a typed error for the failed portion, and alert admins without leaking grades or credentials.
