# Tasks

## 1. Agent and settings

- [x] 1.1 Add `elastic-apm>=6.26.2,<7` through uv and update the lock without downgrading FastAPI/Starlette; verify public Client APIs, client creation/cleanup, and contextvars on Python 3.13.18, record the resolved agent version.
- [x] 1.2 Add `OLYMPIC_APM_*` settings from design, URL/name/sampling validation, SecretStr for the token, and disabled by default; test `.env`, env override, invalid sampling, and absence of the token in the Settings representation.
- [x] 1.3 Implement the app-owned client adapter and lifespan integration without a global singleton/monkeypatch; test no client or network calls when disabled, cleanup on shutdown, bounded waiting, and sequential create_app instances without duplication/leaks.
- [x] 1.4 Configure transport timeout/queue/flush and safe payload: disable body/headers/locals and sanitize secret values; use a recording transport test to check the actual serialized event with test Authorization/Cookie/body/DSN/token values, including an exception message.

## 2. HTTP and background synchronization

- [x] 2.1 Add pure ASGI middleware through the public Client API with HTTP transactions, route template names, and health/static exclusion; use ASGI tests for `/`, API, different IDs, 404/422, outgoing statuses, and no transactions for excluded paths.
- [x] 2.2 Add associated capture of unhandled exceptions and concurrent HTTP transaction isolation; verify a single error event, unchanged FastAPI response, no contextvars mixing, and transaction completion on request cancellation.
- [x] 2.3 Instrument the entire sync_job with a separate background transaction `sync`, passing status and numeric counters; use scheduler tests for ok/partial/failed, fetcher creation/cleanup, exception and cancellation, no sync transactions with the scheduler disabled, and preserved logs.
- [x] 2.4 Check an unavailable receiver, invalid token, and adapter failures: the application starts, API and `/health` work with the database available, and the scheduler retains previous results; test bounded waits and sending new events after receiver recovery.
- [x] 2.5 Add SQL spans through SQLAlchemy engine events within HTTP/background transactions without global instrumentation; verify nesting and concurrent request isolation, SQL errors, no orphan spans, sampling 0, disabled APM, and preserved SQL result on telemetry failures.
- [x] 2.6 Send sanitized SQL in `db.statement`, preserving structure and placeholders while removing comments and string/numeric literals; verify PostgreSQL quoting, unterminated literals, the 10000-character limit, and serialized payload without parameter values or secrets. Update SQL viewing instructions and run the quality gate.

## 3. Self-hosted Elastic Stack

- [x] 3.1 Verify availability of identical specific Elasticsearch/Kibana/APM Server image tags (candidate 9.5.6) and a compatible integration package; record verified versions, implement the `observability` profile with loopback 8200/5601, nonpublic Elasticsearch, memory limits, healthchecks, and separate esdata; check `docker compose config` with and without the profile, without printing secrets.
- [x] 3.2 Add read-only configs and idempotent `elastic-setup` (service accounts) and `apm-setup` with finite retry/timeout for APM integration installation through Kibana; in an isolated Compose project, verify first-start readiness, repeated setup, explicit failure, and no observability dependencies for app.
- [x] 3.3 Update `.env.example`, `.docker-env.example`, README, and AGENTS: opt-in APM enablement, host/container addresses, a matching optional token, stack-only and full Compose startup, environment viewing in Kibana, Elastic/Kibana passwords from .docker-env, host requirements, and preserving/deleting only telemetry; verify consistency with configs and no real credentials in Git.

## 4. Acceptance

- [x] 4.1 In a separate Compose project with a test PostgreSQL database, start the full profile and app with sampling 1; perform API/web UI requests, verify transaction documents in Elasticsearch and the service in Kibana, no health/static transactions, and a forcibly disabled scheduler.
- [x] 4.2 Connect the host application to the same stack through uv and localhost:8200 with environment local; confirm a separate environment in Kibana, an HTTP transaction, and background sync with a test fetcher without requests to real BoincStats.
- [x] 4.3 Stop APM Server and check availability of both application instances; restore it and check new events. Perform down/up without deleting esdata and confirm event persistence. Separately verify regular startup without the profile and with the agent disabled, without changing existing dev volumes.
- [x] 4.4 Run `./quality-gate.sh` without external Elastic: Ruff, mypy, pytest, and coverage of at least 90%; check Docker runtime build with the agent, `git diff --check`, and `openspec validate elastic-apm-observability --strict`; save e2e results and delete only acceptance Compose project resources.
