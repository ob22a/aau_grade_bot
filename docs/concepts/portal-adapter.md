# Portal adapter

The AAU portal adapter is the infrastructure layer that logs in to the university portal, fetches HTML pages, and hands them to parsers.

## Responsibilities

- Fetch the login page and read `__RequestVerificationToken`.
- Submit credentials only after a fresh token is available.
- Classify login responses safely.
- Fetch the home and grades pages after login succeeds.
- Return parsed DTOs, not raw HTML.

## Why the adapter exists separately

The application services should not know the portal's HTML structure or login mechanics. The adapter isolates that contract so the rest of the application can stay stable when AAU changes its layout.

## Important behaviors

- Login is fresh for every scrape.
- The verification token is never reused across attempts.
- Failed credentials are classified immediately and are not retried automatically.
- Portal schema changes raise typed errors with safe diagnostics.

## Data flow

1. Service calls `AAUPortalClient.scrape(...)`.
2. The adapter logs in and fetches the HTML pages.
3. The HTML parsers extract `ProfilePageResult` and `GradeReport`.
4. The service stores or returns the structured results.

## What the adapter does not do

- It does not persist data.
- It does not decide business rules.
- It does not format Telegram replies.
- It does not hide schema change issues; it surfaces them through typed errors.
