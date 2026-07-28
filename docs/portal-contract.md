# AAU portal integration contract

This document defines the evidence required before implementing the AAU
adapter. Secrets must be redacted; do not send a real password, cookie, bot
token, database URL, or cron secret.

## Required samples

1. The login page HTML containing the anti-forgery token and the form action.
2. A successful home-page HTML response, with university ID/name redacted if
   needed, showing department and any term/section information.
3. A successful grades-page HTML response with enough representative courses:
   no grade, released grade, multiple terms, and result/summary if present.
4. A failed-login response/page and the observable status/redirect behaviour.
5. The browser-network details for login and the two page requests: URL,
   method, field names, required headers, and redirect sequence. Redact token
   values.

## Decisions the adapter must honour

- Login is fresh for every scrape; no session/cookie is persisted.
- The verification token is read from the current login page and submitted only
  with that attempt.
- AAU authentication first requests `https://portal.aau.edu.et/` and extracts `__RequestVerificationToken`; `GET /login` is the fallback when the root page does not expose the login form. It then `POST`s to `/login` with form fields `__RequestVerificationToken`, `UserName`, and `Password`. Success is verified by fetching `/Home` and `/Grade/GradeReport`, not merely by trusting the login POST status.
- A grade-row assessment link is a GET to `/Grade/GradeReport/AssessmentDetail` with `academicYearId`, `semesterId`, and `courseId` query parameters. These opaque IDs are parsed from the row; they are never guessed.
- Portal identifiers are validated locally only to reject clearly malformed input. The accepted undergraduate form is `UGR/NNNN/YY`: exactly four digits for `NNNN` and two digits for Ethiopian-year suffix `YY`. The portal  remains the authority for whether an ID exists.
- The adapter returns a profile and grade snapshot in a stable DTO shape, irrespective of AAU HTML details.
- Raw HTML is not logged or stored in production. Sanitised copies may be kept as test fixtures.

## Credential and lockout states

The adapter must classify the final portal response into more than “success”
or “failure”:

| Result | Automated behaviour |
| --- | --- |
| `SUCCESS` | Continue parsing. |
| `INVALID_CREDENTIALS` | Stop immediately; mark stored credentials invalid; do not retry. |
| `LOCKOUT_RISK` | Stop immediately; warn the student, require updated credentials, and start a protective cooldown before the next bot login attempt. |
| `PORTAL_UNAVAILABLE` | Do not mark credentials invalid; retry only under a bounded scheduler policy. |
| `PORTAL_CHANGED` | Do not retry; emit a safe parser/portal alert for administrators. |

AAU returns `200 OK` for these errors, so status codes are not authentication
signals. The client uses Beautiful Soup selectors to read
`div.validation-summary-errors`: `Incorrect username or password.` and
`Invalid credentials.` are an immediate no-retry failure; the latter's
`N more attempt(s)` value becomes `LOCKOUT_RISK` when `N <= 3`. An
unrecognised response containing the login form is classified as unknown, not
successful, and alerts an administrator.
