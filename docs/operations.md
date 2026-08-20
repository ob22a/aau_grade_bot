# Operations and safety

## Endpoints

The bot runs a concurrent web server alongside Telegram polling.

- `GET /` and `GET /health`: return `204 No Content` when the process is alive.

### Triggering the Cron Job
- `POST /cron`: This endpoint triggers the background cohort scan. It requires a constant-time comparison of an `X-Cron-Secret` header with the `CRON_SECRET` defined in your `.env`. Unauthenticated calls receive `401` and do no work.
  
  **How to run it:**
  Configure a service like cron-job.org or Render Cron to hit your deployed URL:
  ```bash
  curl -X POST https://your-app-url.onrender.com/cron \
       -H "X-Cron-Secret: your_cron_secret_here"
  ```

### Viewing Metrics
- `GET /metrics`: Admin-protected endpoint via `X-Admin-Secret`. It returns a JSON snapshot of the system's current state (active users, scanning progress, etc).
  
  **How to run it:**
  ```bash
  curl -X GET https://your-app-url.onrender.com/metrics \
       -H "X-Admin-Secret: your_metrics_secret_here"
  ```

## Runtime composition

- `main.py` starts the HTTP app and optionally Telegram polling.
- `bootstrap.py` builds the HTTP app, the aiogram dispatcher, and the service container.
- `services/container.py` groups the application services for router injection.
- `clients/telegram_adapter.py` wraps the aiogram bot for outbound notifications.

## Concurrency and recovery

- A distributed lock makes cron atomic: only one run may execute at a time.
- A portal semaphore caps concurrent AAU sessions (configured via settings).
- Each concurrent worker creates its own Unit of Work and session.
- Cohort state records a resume cursor in the design docs so interrupted scans can resume safely.
- Pool pre-ping/recycling helps stale connections, but correct session ownership and rollback are the primary protection against closed-connection errors.

## Security rules

- Passwords and decrypted grades are never logged. Logging filters redact known sensitive fields.
- Active FSM states are explicitly cleared (`await state.clear()`) whenever a new command or `/cancel` is issued, preventing input leakage across conversation sessions.
- Input steps validate syntax prior to advancing state, and catch portal authentication/lockout/timeout exceptions to display user-friendly guidance.
- The first unique portal-schema change alerts the admin immediately. Matching failures are counted and aggregated using a safe structural signature; raw HTML and student data are never part of that signature.
- Decrypted passwords live in the smallest practical scope; references are cleared in `finally` after portal login. This reduces retention but cannot guarantee memory erasure in Python.
- Destructive actions require Telegram confirmation. Inactivity deletion first writes an audit/tombstone event, then deletes user-linked data in a committed transaction.

## Local run notes

- If `ENCRYPTION_KEY` is missing, the Telegram polling bootstrap will refuse to start because registration cannot safely encrypt credentials.
- If `REDIS_URL` is not configured, the FSM falls back to in-memory storage for development.
- If `BOT_TOKEN` is missing, the process should remain HTTP-only or fail fast depending on your launch path.
