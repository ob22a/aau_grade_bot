# Async session ownership and connection safety

This project had a real risk of using closed PostgreSQL connections when async sessions lived too long or were shared across tasks.

## The rule

- Every concurrent job gets its own Unit of Work.
- Every Unit of Work gets its own `AsyncSession`.
- The session is committed or rolled back explicitly.
- The session is closed before control leaves the boundary.

## What not to do

- Do not pass one `AsyncSession` into multiple concurrent tasks.
- Do not store the session globally.
- Do not let ORM objects lazily load after the session is closed.
- Do not rely on pool recycling as a substitute for correct lifecycle management.

## What the project does instead

- The engine uses `pool_pre_ping` and `pool_recycle` as safety nets.
- The UoW owns the connection lifecycle.
- Repositories only do persistence work inside the UoW.
- Handlers and services work with detached DTOs and domain-like data.

## Why this matters

This avoids the class of errors where asyncpg raises a closed-connection failure after idle time, retries, or accidental sharing of a session between concurrent work.
