# Connection Pooling: asyncpg, PgBouncer, SQLAlchemy, and Neon

This document explains the complete connection lifecycle used by this project and why the configuration in [`database/connection.py`](../../src/database/connection.py) looks the way it does.

Rather than only describing the configuration, this document explains the architecture underneath PostgreSQL, how PgBouncer works, why prepared statements fail in transaction pooling mode, and why SQLAlchemy is configured differently depending on whether the application connects directly to PostgreSQL or through Neon's connection pooler.

---

# Table of Contents

1. Why Connection Pooling Exists
2. PostgreSQL Architecture
3. What is a Database Connection?
4. PostgreSQL Backend Processes
5. How Direct Connections Work
6. Why Serverless Applications Create Problems
7. PgBouncer Connection Pooling
8. Transaction Pooling
9. Prepared Statements
10. Why Prepared Statements Break with PgBouncer
11. asyncpg Statement Cache
12. SQLAlchemy Pools
13. Why NullPool is Required with Neon Pooler
14. pool_pre_ping
15. pool_recycle
16. Project Configuration
17. Complete Connection Lifecycle
18. Summary

---

# 1. Why Connection Pooling Exists

Opening a PostgreSQL connection is **expensive**.

A new connection is **not** simply opening a TCP socket.

Every new PostgreSQL connection requires:

* TCP handshake
* SSL/TLS negotiation
* User authentication
* Permission checks
* Creating a PostgreSQL backend process
* Allocating memory
* Initializing session state

This entire sequence is relatively expensive compared to simply executing SQL.

If an application opens thousands of connections every second, PostgreSQL spends more time creating backend processes than executing queries.

Connection pooling exists to avoid paying this cost repeatedly.

---

# 2. PostgreSQL Architecture

Unlike many database systems, PostgreSQL is **process-based**, not thread-based.

There is one main server process called the **Postmaster**.

Its only job is listening for incoming client connections.

Every time a client connects, Postmaster forks a brand-new backend process.

```
                PostgreSQL Server

                     Postmaster
                         │
     ┌───────────────────┼────────────────────┐
     │                   │                    │
     ▼                   ▼                    ▼

 Backend #1         Backend #2          Backend #3

  Client A           Client B            Client C
```

Each backend is an independent operating system process.

Every backend owns:

* private memory
* execution context
* transaction state
* prepared statements
* temporary tables
* session variables

Backends **do not share these objects with each other**.

---

# 3. What is a Database Connection?

People often use "connection" to mean different things.

They are actually three separate things.

```
Application
     │
     │ TCP Connection
     ▼
PostgreSQL Server
     │
     ▼
Backend Process
```

A connection consists of:

**Network connection**

The TCP socket between your application and the server.

**Backend process**

The worker process that executes SQL.

**Database**

The entire PostgreSQL server storing all tables and indexes.

The backend is **not** the database.

The backend is simply one worker inside the database server.

---

# 4. Backend Processes

Suppose five applications connect.

```
Application A
Application B
Application C
Application D
Application E
```

PostgreSQL creates:

```
Backend 1
Backend 2
Backend 3
Backend 4
Backend 5
```

Each backend has its own memory.

```
Backend 1

Prepared statements
Temporary tables
Session variables

---------------------

Backend 2

Prepared statements
Temporary tables
Session variables
```

Nothing stored inside Backend 1 exists inside Backend 2.

This detail is extremely important later.

---

# 5. Direct PostgreSQL Connections

Without PgBouncer the mapping is very simple.

```
Application

      │

      ▼

Backend #17

      │

      ▼

Database
```

The application talks to the **same backend** for its entire lifetime.

If the application prepares a statement,

```
PREPARE stmt1
```

the statement remains stored inside Backend #17.

Every future query goes to Backend #17.

Everything works.

---

# 6. The Serverless Problem

Traditional servers usually keep a few long-lived database connections.

Serverless environments do not.

Imagine 2,000 HTTP requests arrive almost simultaneously.

```
Request 1

starts
opens connection
runs query
dies

Request 2

starts
opens connection
runs query
dies

Request 3

starts
opens connection
runs query
dies
```

Every request opens another PostgreSQL connection.

Without pooling:

```
2000 Requests

↓

2000 PostgreSQL Backends
```

Each backend consumes memory.

Eventually PostgreSQL reaches:

```
max_connections exceeded
```

or simply runs out of RAM.

---

# 7. PgBouncer

PgBouncer solves this problem.

Instead of allowing every client to create a PostgreSQL backend, PgBouncer sits in front of PostgreSQL.

```
                    Thousands of Clients

      App
      App
      App
      App
      App
      App

           │
           ▼

        PgBouncer

           │

     Small Pool of Backends

           │
           ▼

       PostgreSQL
```

Now the application is **not connected directly** to PostgreSQL.

Instead,

```
App

↓

PgBouncer

↓

Backend
```

PgBouncer owns the expensive backend connections.

Applications only create lightweight client connections to PgBouncer.

---

# 8. Transaction Pooling

Neon's pooler uses PgBouncer in **Transaction Pooling** mode.

This changes everything.

Instead of permanently assigning one backend to one application,

PgBouncer temporarily borrows one backend.

```
Transaction 1

Application

↓

Backend #3

COMMIT

↓

Backend returned to pool
```

Next query:

```
Application

↓

Backend #8

COMMIT

↓

Returned
```

Then:

```
Application

↓

Backend #2
```

The application **cannot assume it is talking to the same backend anymore**.

---

# 9. Prepared Statements

Prepared statements improve performance.

Normally PostgreSQL performs:

```
Parse

↓

Plan

↓

Execute
```

If the same query executes repeatedly,

```
SELECT *
FROM users
WHERE id=$1
```

PostgreSQL can store the execution plan.

```
PREPARE stmt_users
```

Later:

```
EXECUTE stmt_users
```

No parsing.

No planning.

Only execution.

This is much faster.

However…

Prepared statements live **inside one backend process only**.

---

# 10. Why Prepared Statements Break

Suppose the application prepares a statement.

```
Backend #4

PREPARE stmt_users
```

PgBouncer returns Backend #4 to the pool.

Later:

```
Application

↓

Backend #11
```

Application sends:

```
EXECUTE stmt_users
```

Backend #11 responds:

```
prepared statement does not exist
```

because it has never seen it before.

Likewise, another application may already have created a different statement using the same generated name on that backend, producing errors such as `DuplicatePreparedStatementError`.

The problem is **not** that PgBouncer recreates connections. In fact, it does the opposite: it **reuses** backend connections efficiently. The issue is that **session-specific state (like named prepared statements) is tied to an individual backend**, while transaction pooling intentionally moves clients between different backends after each transaction.

---

# 11. asyncpg Statement Cache

`asyncpg` automatically optimizes repeated queries by creating and caching prepared statements.

This is normally beneficial because, with a direct connection, the client talks to the same backend for its lifetime.

With transaction pooling, however, asyncpg's assumption is no longer valid.

To make asyncpg compatible with PgBouncer, we disable its prepared statement caches:

```python
connect_args={
    "statement_cache_size": 0,
    "prepared_statement_cache_size": 0,
}
```

This prevents asyncpg from relying on named server-side prepared statements that may disappear when PgBouncer switches the backend. Queries still use parameter binding, but asyncpg avoids caching named prepared statements that are unsafe in transaction pooling.

The performance cost is usually modest (often in the single-digit to low double-digit percentage range for workloads that heavily benefit from prepared statement reuse), and it is generally outweighed by the scalability benefits of connection pooling.

---

# 12. SQLAlchemy Connection Pools

SQLAlchemy has its own pooling layer.

It knows nothing about PgBouncer.

```
Application

↓

SQLAlchemy Pool

↓

asyncpg

↓

PgBouncer

↓

PostgreSQL
```

SQLAlchemy supports several pool implementations.

The two relevant ones are:

| Pool      | Behavior                                                                | Best Use                           |
| --------- | ----------------------------------------------------------------------- | ---------------------------------- |
| QueuePool | Keeps connections open and reuses them                                  | Direct PostgreSQL connections      |
| NullPool  | Opens a connection when needed and immediately returns it when finished | External poolers such as PgBouncer |

---

# 13. Why NullPool with PgBouncer?

Using `QueuePool` behind PgBouncer creates two independent pools:

```
QueuePool

↓

PgBouncer

↓

PostgreSQL
```

This is called **double pooling**.

Now SQLAlchemy may hold client connections open even when they are idle, delaying their return to PgBouncer. PgBouncer cannot reuse those client connections for other work, reducing the effectiveness of the external pool.

Instead:

```
Application

↓

NullPool

↓

PgBouncer

↓

PostgreSQL
```

Each operation:

* opens a client connection to PgBouncer,
* executes the work,
* immediately returns the connection.

PgBouncer continues managing the expensive PostgreSQL backend connections efficiently.

---

# 14. pool_pre_ping

`pool_pre_ping=True` is only useful when SQLAlchemy actually keeps a pool.

Before handing out a pooled connection, SQLAlchemy executes:

```sql
SELECT 1
```

If the connection died because of:

* Neon auto-suspend (scale-to-zero)
* network interruption
* server restart
* idle timeout

SQLAlchemy transparently creates a replacement connection instead of failing the request.

With `NullPool`, every connection is already brand new, so there is nothing to pre-ping.

---

# 15. pool_recycle

`pool_recycle` limits the lifetime of pooled connections.

For example:

```python
pool_recycle=300
```

means:

> Any pooled connection older than 300 seconds is closed and replaced before being reused.

This helps avoid stale or long-idle connections when using SQLAlchemy's `QueuePool`.

Like `pool_pre_ping`, it has no practical effect when using `NullPool`, because connections are not retained between uses.

---

# 16. Project Configuration

## When using the Neon `-pooler` endpoint

```python
create_async_engine(
    url,
    poolclass=NullPool,
    connect_args={
        "ssl": True,
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
)
```

Why?

* PgBouncer already manages backend connection reuse.
* `NullPool` avoids double pooling.
* asyncpg caches are disabled to prevent prepared statement errors.
* `pool_pre_ping` and `pool_recycle` are unnecessary because SQLAlchemy is not retaining connections.

---

## When using a direct PostgreSQL endpoint

```python
create_async_engine(
    url,
    connect_args={"ssl": True},
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
)
```

Why?

* SQLAlchemy manages connection reuse with `QueuePool`.
* A client remains associated with the same PostgreSQL backend for the lifetime of the connection, so prepared statements work normally.
* `pool_pre_ping` protects against stale connections after idle periods or server restarts.
* `pool_recycle` periodically refreshes long-lived pooled connections.

---

# 17. Complete Connection Lifecycle

## Direct Connection

```
HTTP Request
      │
      ▼
 SQLAlchemy QueuePool
      │
      │ (reuses the same connection)
      ▼
    asyncpg
      │
      ▼
 PostgreSQL Backend #7
      │
      ▼
   Execute SQL

Next request
      │
      ▼
Same QueuePool Connection
      │
      ▼
Same Backend #7

Prepared statements remain available because the backend never changes.
```

---

## Neon Pooler (`-pooler`)

```
HTTP Request
      │
      ▼
   SQLAlchemy NullPool
      │
      ▼
        asyncpg
      │
      ▼
      PgBouncer
      │
      ├────────► Backend #2
      │            │
      │            ▼
      │         COMMIT
      │
      │      Backend #2 returned
      │
Next request
      │
      ▼
      PgBouncer
      │
      ├────────► Backend #9
      │            │
      │            ▼
      │         COMMIT
      │
      ▼
   Backend returned again

The application sees a continuous logical connection to PgBouncer, but each transaction may execute on a different PostgreSQL backend. Any backend-local state—such as named prepared statements, temporary tables, or session variables—cannot be relied upon across transactions.
```

---

# 18. Summary

| Feature                                                      | Direct PostgreSQL                          | Neon `-pooler` (PgBouncer)                    |
| ------------------------------------------------------------ | ------------------------------------------ | --------------------------------------------- |
| Backend remains the same                                     | ✅ Yes                                      | ❌ No                                          |
| SQLAlchemy `QueuePool`                                       | ✅ Recommended                              | ❌ Avoid                                       |
| SQLAlchemy `NullPool`                                        | ❌ Usually unnecessary                      | ✅ Recommended                                 |
| asyncpg prepared statement cache                             | ✅ Safe                                     | ❌ Disable                                     |
| `pool_pre_ping`                                              | ✅ Recommended                              | ❌ Not needed with `NullPool`                  |
| `pool_recycle`                                               | ✅ Recommended                              | ❌ Not needed with `NullPool`                  |
| Handles large numbers of short-lived/serverless clients well | ⚠️ Limited by PostgreSQL `max_connections` | ✅ Yes                                         |
| Supports backend-local session state across transactions     | ✅ Yes                                      | ❌ No (transaction pooling reassigns backends) |

This structure explains not only **what** the configuration is, but **why** each decision follows from PostgreSQL's architecture, making it much easier to reason about future changes or troubleshoot connection-related issues.
