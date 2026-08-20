# aiogram in this project

`aiogram` is the Telegram framework used to receive updates, maintain conversation state, and dispatch bot commands.

## Why it is used

- It gives the project a router-based dispatcher instead of a single monolithic message handler.
- It supports finite-state conversation flows, which are essential for multi-step registration and admin confirmations.
- It integrates with Telegram polling cleanly while leaving application logic in services.

## How it is used here

- `bootstrap.py` builds a `Dispatcher` and includes routers from `handlers/commands/*`.
- `fsm/states.py` defines the state groups for registration, admin broadcast, account deletion, and section input.
- Handlers only translate Telegram messages into DTOs and pass them to services.
- The `clients/telegram_adapter.py` module wraps `aiogram.Bot` for outbound notifications.

## Important boundaries

- Handlers do not query the database directly.
- Handlers do not parse AAU HTML.
- Handlers do not encrypt data.
- Business decisions live in services.

## Common patterns in the codebase

- `Command("register")` begins the registration flow.
- `FSMContext` stores intermediate conversation data.
- `await state.set_state(...)` advances the user to the next step.
- `await state.clear()` ends the flow after completion or cancellation.

## FSM State Cancellation & Command Interception Policy

To prevent state leaks and ensure predictable user interaction:

1. **Commands Clear Active FSM State**: Every top-level command handler (`/start`, `/register`, `/grades`, `/metrics`, `/broadcast`, `/setsetting`, `/cancel`) calls `await state.clear()` upon execution. If a user is mid-registration and sends `/start` or `/grades`, the previous pending step is immediately cancelled and the new command is executed.
2. **Command Interception in Input Steps**: Step handlers waiting for input (e.g. `RegistrationFSM.university_id`, `RegistrationFSM.password`, `AdminBroadcastFSM.message`) check if `text.startswith("/")`. If a command string is received, the handler calls `await state.clear()` and notifies the user that the operation was cancelled due to the incoming command.
3. **Explicit `/cancel` Command**: Users can send `/cancel` or type `cancel` at any point during a multi-step conversation to cleanly abort the active operation and return to idle state.
4. **Input Format Validation Retries**: Step validators (e.g. `normalize_aau_undergraduate_id`) check syntax before advancing state. If format validation fails (e.g. `ValueError`), the handler displays format guidance (e.g. `UGR/NNNN/YY`) and keeps the FSM state active so the user can re-type their input without restarting the command.
5. **Comprehensive Error Handling**: All service calls inside step handlers are wrapped in `try...except` blocks for domain exceptions (`PortalAuthenticationError`, `PortalLockoutRiskError`, `PortalTimeoutError`, `PortalUnavailableError`, `PortalSchemaChangedError`, `ValueError`). On error, a user-friendly error message is displayed and `await state.clear()` is called.

## Operational notes

- The current bootstrap uses in-memory storage by default and Redis storage when `REDIS_URL` is configured.
- Telegram polling is optional and can be disabled via settings when the process is serving HTTP only.
