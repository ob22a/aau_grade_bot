# 008. Handlers, services, and repositories are separated, with manual dependency injection

* **Status:** Accepted
* **Date:** 2026-07-08

## Context
* **The System/Problem:** Telegram message handlers currently execute business logic, manage data access, and execute external scraper operations inline within a single function.
* **The Pain Point:** Testing core logic requires fabricating mock Telegram `Message` objects and executing them through the dispatcher framework. Furthermore, database operations and external scraper instances are tightly coupled inside handlers, preventing isolated testing without extensive runtime monkeypatching.
* **The History:** Inline handling worked for rapid prototyping, but blending HTTP/Telegram transport mechanics with business logic makes the codebase brittle and untestable.

## Decision
**The architecture will be split into three decoupled layers connected exclusively via manual constructor dependency injection. No automated DI container framework will be used.**

* **Handlers:** Parse incoming Telegram updates, invoke a corresponding service layer method, and format the output response.
* **Services:** Contain pure business logic and interact strictly with repository abstractions, remaining decoupled from framework types.
* **Repositories:** Encapsulate raw database access (SQLAlchemy syntax, session tracking) behind concrete boundary interfaces.

## Alternatives Considered
* **Use a third-party DI Container Library (e.g., `punq`, `dependency-injector`):** Rejected. At the project's current scale, explicit manual injection in `__init__` constructor signatures is easily readable and lacks framework overhead.
* **Adopt strict Hexagonal Architecture (Ports and Adapters):** Rejected. Abstracting the Telegram communication layer via an outbound messaging port provides zero return on investment, as this application is fundamentally coupled to Telegram and will not change its transport mechanism.

## Consequences & Safety Steps
* **The Trade-off:** Developing a new feature now requires touching files across multiple layers, adding architectural boilerplate. This ceremony can be bypassed with direct pass-through shortcuts for simple, logic-free queries.
* **Crypto/Code Dangers:** **CRITICAL:** Repository boundary interfaces must only accept and return pure domain objects or dataclasses. If an implementation leaks live SQLAlchemy ORM model instances or raw execution `Row` objects into the service layer, the boundary fails, causing dependency bleeding and silent testing failures.
* **Open Questions / Future Work:** As decided in ADR 007, all FSM conversation transition validation rules belong directly inside the service layer, as they constitute core application business rules rather than transport-routing concerns.