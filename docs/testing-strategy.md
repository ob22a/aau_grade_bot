# AAU Grade Bot — Testing Strategy

The target is meaningful critical-path coverage, security validation, and empirical performance benchmarking rather than vanity code coverage metrics.

---

## 1. Coverage Goals

- **Portal Scraping & Parsing**: Token extraction, profile parsing, grade report formatting, assessment breakdown parsing, and schema change detection.
- **Crypto & Vault**: AES-256-GCM encryption/decryption round-trips, key generation, associated data validation, and tamper detection.
- **Database & Connection Pooling**: SQLAlchemy async unit of work, repository isolation, auto-detection of Neon pooler endpoints (`NullPool` + `statement_cache_size=0`), and zero connection leakage.
- **Dispatcher & Handlers**: `/start`, `/register`, `/grades` (with inline year/semester pagination), `/metrics` admin commands, and FSM conversation state.
- **Stress & Scalability**: Load testing up to 1,000 concurrent users across registrations, grade reads, cohort scanning under user load, real PostgreSQL pooling, and notification rate-limit verification.

---

## 2. Test Suite Architecture

| Test Layer | Directory / Path | Purpose & Scope | Examples |
|---|---|---|---|
| **Unit Tests** | `tests/unit/` & `tests/test_*.py` | Fast domain, parser, crypto, and service logic tests using in-memory mocks | Malformed grade HTML, invalid AAU ID normalization, AES-256-GCM tamper test, connection config auto-detection |
| **Integration Tests** | `tests/integration/` | End-to-end dispatcher routing, HTTP server auth, FSM transition flows | `/health` 204 response, `/metrics` secret validation, `/register` user interaction state machine |
| **Contract Tests** | `tests/contract/` | External port contract compliance | Portal client token extraction, notification sender formatting |
| **Stress Suite** | `tests/stress/` | Scalability, throughput, latency percentiles, and DB pool stability up to 1,000 users | Scenarios A–E (Registration, Grade Reads, Cohort Scan, DB Pool, Telegram Rate Limits) |

---

## 3. Stress Test Scenarios & Capacity Benchmarks

The stress testing suite in `tests/stress/` uses `asyncio.gather` and `time.perf_counter` to record latency percentiles (P50, P95, P99) and error rates:

- **Scenario A (`test_scenario_a_registration.py`)**: Ramps concurrent registrations from 50 to 1,000 users. Evaluates AES-256-GCM cipher encryption throughput and FSM queueing under backpressure.
- **Scenario B (`test_scenario_b_grades.py`)**: Ramps concurrent grade reads from 50 to 1,000 users with a 50/50 mix of cache hits (< 1ms) and cache misses, plus rapid inline term pagination.
- **Scenario C (`test_scenario_c_cohort_scan.py`)**: Simulates background cron cohort scanning (10 cohorts / 100 users) running concurrently with 220 user grade requests to verify zero request starvation and portal semaphore fairness (`limit=3`).
- **Scenario D (`test_scenario_d_db_pool.py`)**: Uses `testcontainers[postgres]` to run 200+ rapid open/execute/close session cycles against a **real PostgreSQL instance**, verifying 0 prepared statement errors and 0 connection leaks.
- **Scenario E (`test_scenario_e_notifications.py`)**: Benchmarks raw notification dispatch throughput and verifies Telegram's 30 msg/sec global and 1 msg/sec per-chat rate limits.

---

## 4. Test Execution Commands

```bash
# Run unit and integration tests (123 tests)
python -m pytest tests/ --ignore=tests/stress -v

# Run stress scenarios A, B, C, E (mocked backends, no Docker required)
python -m pytest tests/stress/ -v -s -k "not scenario_d"

# Run Scenario D (real PostgreSQL via Docker Testcontainers)
python -m pytest tests/stress/test_scenario_d_db_pool.py -v -s

# Run all tests in the repository
python -m pytest tests/ -v -s
```
