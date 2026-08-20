# 021. Failed AAU Credentials Are Never Automatically Retried

* **Status:** Accepted
* **Date:** 2026-07-16

## Context

* **The System/Problem:** The application authenticates to the AAU portal on behalf of students to perform automated operations such as scheduled scraping and account synchronization. Authentication depends on user-provided AAU credentials and is subject to the portal's security policies.

* **The Pain Point:** The AAU portal may lock user accounts after repeated failed authentication attempts. If the application automatically retries invalid credentials during scheduled execution, it risks locking a student's account without any action from the student. The application must therefore distinguish between permanent authentication failures and temporary operational failures.

* **The History:** Earlier retry strategies treated authentication failures similarly to transient infrastructure failures. This created the risk of repeatedly submitting invalid credentials during automated scraping, potentially triggering account lockout and negatively impacting users.

## Decision

**A portal authentication failure determined to be caused by invalid credentials SHALL immediately mark the stored credentials as invalid, disable automated scraping for that user, record a safe audit event, and require the student to re-authenticate before automated access resumes.  The scheduler SHALL select another eligible representative instead of retrying the affected user. Authentication failures caused by transient conditions, such as network interruptions or server-side (5xx) errors, SHALL be classified separately and MAY follow a bounded retry policy.**

## Alternatives Considered

* **Automatically retry all authentication failures:** Rejected. Repeatedly submitting invalid credentials may trigger account lockout on the AAU portal and negatively affect users without their knowledge.

* **Treat every authentication failure as permanent:** Rejected. Temporary infrastructure failures would unnecessarily disable automated scraping and require users to re-authenticate even though their credentials remain valid.

* **Ignore authentication failures and continue scheduling the same user:** Rejected. This risks repeated failed login attempts, unnecessary portal traffic, and increased likelihood of account lockout.

## Consequences & Safety Steps

* **The Trade-off:** Automated scraping for affected users stops until they successfully re-authenticate. This temporarily reduces automation but prioritizes protection of user accounts over uninterrupted background processing.

* **Crypto/Code Dangers:**

  * Portal authentication failures MUST be classified accurately to distinguish invalid credentials from transient operational failures.
  * No execution path SHALL repeatedly retry an authentication failure classified as invalid credentials.
  * Audit records MUST contain only safe operational information and MUST NOT include passwords or other sensitive authentication data.
  * Scheduler logic MUST exclude users with invalid credentials from automated scraping until they have successfully re-authenticated.

* **Open Questions / Future Work:**

  * Monitor portal behavior to ensure authentication failure classifications remain accurate if AAU changes its responses.
  * Review retry thresholds for transient failures based on operational experience.
  * Reevaluate credential recovery workflows as additional account management features are introduced.
