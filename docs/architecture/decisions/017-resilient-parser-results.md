# 017. Parsers Return Data and Warnings, Then Raise Typed Failures for Unsafe Omissions

* **Status:** Accepted
* **Date:** 2026-07-16

## Context

* **The System/Problem:** The application extracts information from AAU portal HTML pages to perform operations such as registration, profile synchronization, and grade updates. These pages are outside the application's control and may change over time as the university modifies their structure or presentation.

* **The Pain Point:** HTML changes do not always invalidate an entire page. Some differences are harmless, such as cosmetic layout changes or optional fields disappearing, while others affect data required for correctness. Treating every parser difference as a fatal error discards information that could still be safely used. Conversely, silently accepting missing or ambiguous correctness-critical data—such as a missing grade section—could cause incorrect application behavior, including inaccurate notifications or inconsistent state.

* **The History:** Earlier parser behavior risked treating all parsing problems the same. This made it difficult to distinguish between recoverable variations that should be reported as warnings and missing data that should stop processing to preserve correctness.

## Decision

**Parsers SHALL return immutable parsed DTOs together with warnings describing recoverable differences encountered during parsing. If required data for a correctness-critical operation is missing, incomplete, or ambiguous, the parser SHALL raise a typed parser exception instead of producing partial results. Parser exceptions SHALL contain only safe diagnostic information, such as the page type, parser rule, or selector that failed, and SHALL NOT include credentials, authentication tokens, or raw grade data. The application SHALL report these failures to administrators for investigation.**

## Alternatives Considered

* **Treat every parser difference as a fatal error:** Rejected. Minor HTML variations would unnecessarily prevent processing of otherwise valid data, reducing the application's resilience to harmless portal changes.

* **Ignore missing or ambiguous data and continue processing:** Rejected. Continuing with incomplete correctness-critical information risks making incorrect business decisions, such as reporting grade changes that cannot be confidently determined.

* **Return partial results without distinguishing warnings from failures:** Rejected. Callers would be unable to determine whether parsing completed safely or whether essential information was missing.

## Consequences & Safety Steps

* **The Trade-off:** Parser implementations must classify parsing outcomes into recoverable warnings and correctness-critical failures. Test fixtures must cover both expected HTML and known structural variations to ensure parser behavior remains predictable as the portal evolves.

* **Crypto/Code Dangers:**

  * Parser exceptions MUST NOT expose sensitive information such as credentials, session identifiers, authentication cookies, or raw grade data.
  * Correctness-critical operations MUST NOT proceed when required data cannot be parsed with confidence.
  * Warnings MUST NOT be interpreted as successful validation of correctness-critical information; they indicate recoverable differences only.

* **Open Questions / Future Work:**

  * Expand parser fixture coverage as additional portal layouts or HTML variations are discovered.
  * Define common warning categories to improve monitoring and operational reporting.
  * Review parser rules periodically to remove obsolete selectors as the portal evolves.
