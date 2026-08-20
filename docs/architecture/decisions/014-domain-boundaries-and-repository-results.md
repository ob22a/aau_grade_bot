# 014. Repositories Return Domain Data, Never ORM Instances

* **Status:** Accepted
* **Date:** 2026-07-16

## Context

* **The System/Problem:** The application uses the Repository pattern with SQLAlchemy as the persistence layer. Application services consume repositories to retrieve and modify business data.

* **The Pain Point:** Returning SQLAlchemy ORM instances from repositories exposes persistence-layer behavior to the application layer. ORM instances are attached to a SQLAlchemy `Session`, allowing lazy loading of relationships and automatic change tracking. This means services can unintentionally trigger database queries or persist modifications simply by mutating an object that is still managed by the session. Consequently, business logic becomes coupled to SQLAlchemy concepts such as sessions, lazy loading, identity maps, expiration, and dirty checking.

* **The History:** Earlier repository implementation plans exposed ORM models directly to services. This made services dependent on SQLAlchemy, increased the likelihood of `DetachedInstanceError` after a session closed, complicated unit testing, and introduced the possibility of implicit database updates through session-managed objects.

## Decision

**Repositories SHALL accept and return domain models or Pydantic DTOs. SQLAlchemy ORM models SHALL remain internal to repository implementations. Repository implementations SHALL map between ORM models and domain models at the persistence boundary. Application services SHALL NOT import or depend on `database.models` or other SQLAlchemy ORM types.**

## Alternatives Considered

* **Return SQLAlchemy ORM instances directly:** Rejected. This couples business logic to SQLAlchemy, permits lazy loading outside repository boundaries, and allows session-managed objects to be modified and later persisted implicitly when the session is committed.

* **Expose the SQLAlchemy `Session` to application services:** Rejected. This leaks infrastructure concerns into the application layer, encourages direct database manipulation, makes transactional boundaries difficult to enforce, and weakens the separation of concerns established by the Repository pattern.

## Consequences & Safety Steps

* **The Trade-off:** Repository implementations require explicit mapping between ORM models and domain models, introducing additional mapping code and a small maintenance overhead. This cost is accepted in exchange for a clean separation between business logic and persistence.

* **Crypto/Code Dangers:**

  * Returning ORM instances may cause unexpected lazy-loading queries after a session has been closed, resulting in runtime errors such as `DetachedInstanceError`.
  * ORM instances attached to an active session are automatically tracked for changes (dirty checking). Mutating these objects can result in unintended database updates during a later `commit()`, even when persistence was not explicitly requested by the service.
  * Mixing domain models and ORM models within the application layer increases coupling and makes it more difficult to reason about transaction boundaries and persistence behavior.

* **Open Questions / Future Work:**

  * Evaluate automated mapping libraries if manual mapping becomes a maintenance burden.
  * Define project-wide conventions for mapping nested aggregates and relationships between domain models and ORM models.
  * Reassess the approach if the persistence layer changes or if another ORM is adopted in the future.
