# Design

## Context

See `proposal.md`. The application is created by a FastAPI factory and manages the engine/scheduler through lifespan. Configuration uses the `OLYMPIC_` prefix and reads `.env` locally; in Compose, container settings come from `.docker-env`. The scheduler is forcibly disabled in the container. `run_sync` returns `SyncResult` with `ok/partial/failed` statuses, so absence of an exception does not mean the entire synchronization succeeded.

Current Python 3.13.18, FastAPI 0.142.2, Starlette 1.7.0, and asyncpg 0.31.0 are pinned in uv.lock. Elastic documentation supports Python 3.13 but describes the built-in Starlette integration only for `<1`. This prevents unconditional use of `elasticapm.contrib.starlette.ElasticAPM`, but the public Client API allows instrumenting custom code.

## Goals / Non-Goals

**Goals:** HTTP, SQL, and scheduler observability through one self-hosted stack, viewing sanitized SQL in span details, distinguishing local/docker environments, a reproducible Compose profile, and preserving application operation when APM is unavailable.

**Non-Goals:** browser RUM, OpenTelemetry/EDOT, Fleet Server/Elastic Agent, forwarding all file logs, separate infrastructure monitoring, mandatory SQL spans for all drivers, automatic monitoring of CLI import/export and migrations, API/database changes. Do not downgrade FastAPI/Starlette for integration.

## Decisions

### 1. Public agent API and ASGI

Add runtime dependency `elastic-apm>=6.26.2,<7` through uv, resolve and record a specific version in the lock. Verify its public APIs on the current Python; do not change existing FastAPI/Starlette versions. A new `apm.py` module encapsulates client creation/cleanup, HTTP middleware, and background transaction context.

Use a small pure ASGI middleware with `Client.begin_transaction`, `end_transaction`, `capture_exception`, and outcome setting through the public API. Do not use BaseHTTPMiddleware or rely on the built-in integration with an unsupported Starlette range. Do not enable global library monkeypatching: add SQL spans through events only on the application's own SQLAlchemy engine. This also simplifies independence of multiple `create_app()` instances in tests.

The wrapper passes through lifespan and non-HTTP scopes, `/health`, `/static`, and `/static/…`; for other HTTP requests it intercepts `http.response.start`. The name is determined after routing as `METHOD <route.path>`, or `METHOD unknown route` for an unknown route, without IDs/query string. HTTP result is the code class (`HTTP 2xx`, etc.); outcome follows server rules: 5xx failure, 4xx are not treated as unhandled exceptions. On exception, record one error associated with the current transaction and re-raise the original exception; do not change FastAPI handling. Concurrent request tests for contextvars isolation are mandatory.

### 1.1. SQL spans and query text

When an APM client is created, attach `before_cursor_execute`, `after_cursor_execute`, and `handle_error` handlers to `engine.sync_engine`. Through `elasticapm.capture_span`, create `db.postgresql.query` spans within the current sampled HTTP/background transaction; without a current transaction, at sampling 0, or with APM disabled, no spans are created. Choose names from a fixed set of operations `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `WITH`, otherwise `SQL`. End the span after SQL execution or error, preserving original database behavior and concurrent request isolation. Telemetry failures must not replace the query result.

Send SQL through `extra.db.statement` and `extra.db.type=sql`. Preserve structure, table/column names, and parameter placeholders; replace string literals, including PostgreSQL escape strings and dollar quoting, and numeric literals with `?`. Remove single-line and nested block comments. Do not send parameter values, connection URL, or settings. Limit sanitized SQL to 10000 characters after sanitization so truncation cannot expose part of an original literal. Check unterminated literals, comments, and payload size in separate tests.

SQL text is available only in new spans after application restart; old events are not supplemented. `GET /` serves HTML without SQL; use API transactions, for example `GET /api/medals`, to view SQL.

### 2. Configuration

| Setting | Default | Purpose |
|---|---|---|
| `OLYMPIC_APM_ENABLED` | `false` | Agent enablement |
| `OLYMPIC_APM_SERVER_URL` | `http://127.0.0.1:8200` | Receiver URL; for app in Compose — `http://apm-server:8200` |
| `OLYMPIC_APM_SERVICE_NAME` | `olympic-boinc` | Shared service name |
| `OLYMPIC_APM_ENVIRONMENT` | `local` | Specify `docker` in `.docker-env.example` |
| `OLYMPIC_APM_SECRET_TOKEN` | absent | Transport credential; store as SecretStr |
| `OLYMPIC_APM_TRANSACTION_SAMPLE_RATE` | `1.0` | Proportion of sampled transactions, range 0..1 |

The agent is disabled in `.env.example`/`.docker-env.example`; provide exact enablement instructions and the correct address alongside. Take service version from installed package metadata. Validate name against the allowed Elastic format, http/https URL without credentials, and sampling. Do not introduce a second documented `ELASTIC_APM_*` set; state in README that they should not be set alongside OLYMPIC settings because the agent has its own precedence. Disable central configuration (`CENTRAL_CONFIG=false`) so project values cannot be changed from Kibana.

Do not collect body (`CAPTURE_BODY=off`), headers (`CAPTURE_HEADERS=false`), or local variables (`COLLECT_LOCAL_VARIABLES=off`). Pass only necessary safe HTTP fields into the ASGI context; do not copy the entire scope/Settings. Do not forward error text from `SyncResult.errors` or DSNs. Add a processor to sanitize credential URLs/known secret fields in error events; test actual serialized payload with test values, including a secret in an exception message.

### 3. Lifecycle and fault tolerance

Create the client in lifespan only when APM is enabled, store it in app.state, and pass it to the scheduler through an explicit adapter/optional argument. Before initialization and after closing, the adapter is a no-op. HTTP middleware reads the app-owned client, does not create a client on import, and does not use a global singleton as the owner.

The agent transport sends in the background; set finite limits: send timeout 2 seconds, send interval up to 5 seconds, agent queue limit 500 events. Verify exact parameter names against the selected agent version. Shutdown closes the client with bounded waiting of no more than 5 seconds outside the event loop. Do not synchronously check receiver availability before every request; transport errors are visible through the diagnostic logger. APM adapter errors must not replace the application result: contain them, log diagnostics, and continue the main code. Do not hide Settings validation errors.

Do not tie `/health` to Elasticsearch/Kibana/APM. The recovery guarantee is sending new events, not unconditional delivery of a lost queue. APM tests use a local recording transport or stub by default and never send events to a real stack.

### 4. Background synchronization

On actual entry to `sync_job`, start a transaction of type `background`, name `sync`; cover the entire run, including fetcher creation and cleanup. Set result from `SyncResult.status`; outcome success only for `ok`, failure for `partial/failed`. Pass `added/skipped/deferred` counters as numeric context. For an unexpected exception, use `capture_exception` and result `failed`. In this iteration, handled individual page errors are represented by status and counters without duplicating each as a separate error event.

End the transaction in finally even on cleanup failure or cancellation; for cancellation, result `cancelled`, outcome unknown. Preserve normal logs, fetcher closing, max_instances, and schedule. For scheduler_enabled=false, create no background transactions. Do not place telemetry inside `run_sync` business logic, so CSV/shared persistence do not depend on APM.

### 5. Self-hosted Compose profile

Add `elasticsearch`, `kibana`, `apm-server`, and one-shot `elastic-setup` and `apm-setup` to the `observability` profile. Choose standalone APM Server: it requires neither Fleet Server nor Elastic Agent. Pin identical specific Elasticsearch/Kibana/APM Server image tags; the initial candidate is **9.5.6**, listed in current Elastic documentation. Before implementation, verify all three tags exist and the integration package is compatible; do not use `latest`.

Elasticsearch is single-node with a separate named `esdata` volume, memory limit, and no published 9200. Based on verification and user agreement, enable standard Elasticsearch security: the Fleet API requires authentication and authorization. For the local profile, use internal Elasticsearch/Kibana HTTP connections with authentication and authorization; only `127.0.0.1:8200:8200` and `127.0.0.1:5601:5601` are published. The APM secret token is optional; when set, the same token is used by the agent and receiver. The secret comes from env_file into server config, without substitution into command arguments/reports. Describe actual resources and necessary Elasticsearch host settings in README; do not change machine sysctl automatically. Public access, TLS, and multi-node deployment are outside this local profile.

Credentials are set in `.docker-env`: `ELASTIC_PASSWORD` for initial setup and Kibana login as `elastic`, `KIBANA_SYSTEM_PASSWORD` for kibana_system, `APM_WRITER_PASSWORD` for separate apm_writer, and `KIBANA_ENCRYPTION_KEY` of at least 32 characters. After Elasticsearch is ready, `elastic-setup` idempotently sets the kibana_system password and creates a restricted apm_writer role/user to write APM traces/logs/metrics; Kibana starts after it. APM Server uses apm_writer rather than a superuser.

Mount config files in `docker/` read-only. Services receive settings from `.docker-env`; do not rely on compose substitution of secrets from `.env`. Set image versions to fixed values. Elasticsearch, Kibana, and APM Server have healthchecks; app still depends only on PostgreSQL readiness. APM Server depends on ready Elasticsearch and completed setup. Observability availability is not added to application dependencies.

`apm-setup` waits for Elasticsearch/Kibana with finite timeout/retry and idempotently installs bundled `apm-9.5.6.zip` from the official Kibana image through the authenticated Kibana API with `kbn-xsrf`; Kibana allows the pinned version from its own bundled package in air-gapped mode, so no registry is needed; it checks the installed compatible version. This step is necessary: APM Server HTTP port readiness alone does not prove it can index events. Pin a compatible specific package version alongside images based on registry/API verification; do not assume it automatically equals the image patch number. On setup error, the container exits nonzero, while app continues starting. Repeated execution does not reinstall assets unnecessarily.

### 6. Startup scenarios

**Application in Compose:** enable `OLYMPIC_APM_ENABLED=true` in `.docker-env`, set `OLYMPIC_APM_SERVER_URL=http://apm-server:8200`, environment `docker`, then `docker compose --profile observability up -d --build`.

**Application on the host:** start only the stack with `docker compose --profile observability up -d elasticsearch kibana apm-setup apm-server`; enable APM in `.env`, URL `http://127.0.0.1:8200`, environment `local`; run the existing command `uv run --locked uvicorn olympic_boinc.api.app:create_app --factory`. The host app uses its existing PostgreSQL configuration.

Open `http://127.0.0.1:5601`, log in as `elastic` with the password from `.docker-env`, and select service `olympic-boinc` in APM/Applications and the desired environment. End-to-end smoke is mandatory: the event is not only accepted by intake but also found in Elasticsearch and displayed in Kibana. `docker compose down` preserves esdata; deleting observability data is a separate explicitly documented operation that does not delete the PostgreSQL volume.

## Risks / Trade-offs

- [Unsupported built-in Starlette integration] → public Client API + pure ASGI, tests of real ASGI responses/errors/context isolation without downgrading libraries.
- [Healthchecks are green but APM does not index] → automatic integration setup and e2e verification of a document in Elasticsearch/Kibana.
- [A large stack consumes memory and starts slowly] → separate profile, limits, and documented host requirements; the regular gate does not start Elastic.
- [Secrets captured through exception context] → minimal context, disabling headers/body/locals, and serialized payload validation.
- [Long background synchronization and cancellation] → explicit transaction completion on all paths; do not change business database transactions.

## Migration Plan

Add the dependency and adapter with APM disabled, then the stack profile and enablement documentation. Run unit/ASGI/scheduler tests and the quality gate without external Elastic; separately perform e2e for both execution methods in an isolated Compose project and test database. Check repeated startup with esdata preserved, an unavailable receiver, and APM disablement. Rollback: disable `OLYMPIC_APM_ENABLED` and stop the profile, restoring the previous package if needed; PostgreSQL schema and data do not change.

## References

- [Elastic: supported technologies](https://www.elastic.co/docs/reference/apm/agents/python/supported-technologies).
- [Elastic: public Python Client API](https://www.elastic.co/docs/reference/apm/agents/python/api-reference).
- [Elastic: Python agent settings and precedence](https://www.elastic.co/docs/reference/apm/agents/python/configuration).
- [Elastic: standalone APM Server](https://www.elastic.co/docs/solutions/observability/apm/apm-server/binary).
- [Elastic: installing the integration through Kibana](https://www.elastic.co/docs/solutions/observability/apm/apm-server/fleet-managed).
