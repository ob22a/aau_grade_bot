# 018. External Systems Are Accessed Through Explicit Ports

* **Status:** Accepted
* **Date:** 2026-07-16

## Context

* **The System/Problem:** The application communicates with several external systems, including the AAU portal, Telegram, Redis, encryption services, time providers, and distributed locking mechanisms. These systems provide infrastructure capabilities that support business operations but are not part of the application's core domain logic.

* **The Pain Point:** Allowing application services to depend directly on concrete libraries or SDKs couples business logic to infrastructure implementations. Replacing an external system, introducing an alternative implementation, or writing isolated unit tests becomes more difficult because services depend on specific APIs instead of application-defined contracts.

* **The History:** As the application integrated additional external services, infrastructure concerns risked spreading into the application layer. This increased coupling between business logic and third-party libraries and reduced flexibility for testing and future system changes.

## Decision

**Application services SHALL depend only on small, application-defined protocols (ports) representing required capabilities such as portal access, notifications, caching, encryption, time, and distributed locking. Concrete implementations (adapters) SHALL implement these protocols and SHALL be wired into the application through manual constructor injection in the composition root. The AAU portal and Telegram integrations SHALL serve as the initial adapters for their respective ports. Telegram update handlers themselves SHALL remain part of the application's boundary and SHALL NOT be abstracted behind ports.**

## Alternatives Considered

* **Depend directly on third-party libraries within application services:** Rejected. This tightly couples business logic to infrastructure implementations, making testing, replacement, and maintenance more difficult.

* **Create a single infrastructure service exposing all external capabilities:** Rejected. This produces an overly broad interface, increases coupling between unrelated concerns, and violates the principle of keeping dependencies focused on specific capabilities.

* **Abstract every framework component, including Telegram handlers:** Rejected. Telegram handlers already define an application boundary. Introducing additional abstraction around them would add complexity without improving separation of concerns.

## Consequences & Safety Steps

* **The Trade-off:** Each external capability requires both a protocol and at least one adapter implementation, introducing additional interfaces and dependency wiring. This additional structure is accepted to maintain a clear separation between application logic and infrastructure.

* **Crypto/Code Dangers:**

  * Application services MUST NOT depend on concrete infrastructure libraries or instantiate external clients directly.
  * Adapters MUST faithfully implement the behavior defined by their corresponding ports to ensure services remain independent of implementation details.
  * Infrastructure-specific exceptions SHOULD be translated into application-level failures before crossing into the application layer, preventing third-party APIs from leaking through service interfaces.

* **Open Questions / Future Work:**

  * Introduce additional adapters as new external systems are supported without modifying application services.
  * Review whether additional infrastructure capabilities require new ports as the application evolves.
  * Reevaluate dependency injection strategy if the application's composition root becomes significantly more complex.
