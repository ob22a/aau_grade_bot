# Contributing

Before adding a feature, identify its use case, its application service, and the ports it needs. Add or update an ADR when a decision changes a dependency rule, data invariant, security property, or operating behaviour.

## Design rules

- Keep handlers thin: no SQLAlchemy, portal parsing, or business policy in a handler.
- Keep ORM models inside infrastructure. Repository interfaces return domain models or Pydantic DTOs.
- Give every concurrent operation a separate Unit of Work; never share an `AsyncSession` across `asyncio.gather` tasks.
- Do not create unsupervised background tasks in services. Publish an event to the dispatcher instead.
- Add a unit test with every parser rule or domain policy, and a sanitised regression fixture for every real portal change.
- Treat credentials, raw portal HTML, grade values, bot tokens, and cron secrets as sensitive. Do not put them in logs, fixtures, commits, or errors.

## Documentation rules

- Update the concept docs when a library or subsystem becomes confusing enough to need its own explanation.
- Keep `docs/README.md` as the table of contents.
- Prefer one concept per page in `docs/concepts/`.
- When changing a runtime behavior, update both the code and the operating documentation.

## Code review checklist

- Does the change preserve session ownership?
- Does it leak sensitive data?
- Is there a regression test or fixture for the new rule?
- Does it keep handlers thin and services testable?
- Does it require a new ADR?
