# Elastic APM verification — 2026-11-10

## Versions and implementation

- Python 3.13.18; elastic-apm 6.26.2; FastAPI 0.142.2 and Starlette 1.7.0 preserved.
- Elasticsearch, Kibana, APM Server: official 9.5.6 images; bundled APM integration 9.5.6.
- Pure ASGI middleware and public Client API; a separate client per application lifespan.
- HTTP route templates, associated error capture, background `sync` with statuses and numeric context.
- Queue of 500 events, transport timeout 2 s, sending every 5 s, shutdown wait up to 5 s. Delivery of events during a failure is not guaranteed.
- Serialized payload checked with recording transport: body, Authorization/Cookie, locals, credential DSN, and APM token absent.

## Automated checks

`UV_PROJECT_ENVIRONMENT=/home/mikhail/venvs/olympic_boinc_uv ./quality-gate.sh`:

- Ruff: passed.
- mypy: passed, 45 source files.
- pytest: **183 passed, 1 deselected** (live test).
- Line coverage: **94.56%**, threshold 90%; `apm.py` — 100%.
- Tests require no external Elastic: recording transport, local fake intake (503/401/202), absent receiver, adapter errors, and bounded shutdown.
- Bootstrap tests check a service role without superuser, no reinstallation, a pinned integration version, finite retries, and no responses/secrets in messages.
- `git diff --check` and `openspec validate elastic-apm-observability --strict`: passed.
- Docker runtime built successfully from uv.lock; agent installed without dev/load extras.

## Real stack and both execution methods

Used a separate Compose project `olympic-apm-qa`, its own test credentials,
PostgreSQL/esdata, and random loopback ports. User `.env`/`.docker-env`
and existing dev volumes were unchanged. External BoincStats was not contacted.

- Compose config checked with and without the profile, without printing secrets. App depends only on db. Elasticsearch is not published; Kibana and intake are on loopback.
- Container app serves `/`, `/api/medals`, `/api/challenges/years`, `/health`, and static with HTTP 200; scheduler forcibly disabled.
- Elasticsearch contains `GET /`, `GET /api/medals`, `GET /api/challenges/years` with `service.environment=docker`; no health/static transactions.
- Host application started through `uv run --locked --no-sync`, connected to loopback intake and test PostgreSQL. HTTP events have environment `local`.
- The host scheduler ran real `run_sync` with a fetcher using local HTML fixtures. Found a `sync` document, type `background`, result `ok`, outcome `success`, custom `{added: 0, skipped: 0, deferred: 1066}`.
- Logged in to Kibana through Chromium; service `olympic-boinc` is visible separately when selecting environment `local` and `docker`.
- With APM Server stopped, both applications continue responding to `/health`, `/api/medals`, `/`; after receiver startup, the document count increased from 8 to 11.
- After `down` without `-v` and another `up`, all 11 documents were preserved.
- Fully automatic first startup with empty test pgdata/esdata succeeded: service credentials and bundled integration installed without manual actions, healthchecks green, `GET /` and `GET /api/medals` written to Elasticsearch.
- Repeated `elastic-setup` and `apm-setup` succeeded. Setup with empty ELASTIC_PASSWORD exits nonzero with a clear message; the main API remains available.
- Additional project `olympic-apm-basic-qa` started without the profile: only db/app run, HTTP 200, no APM client created, scheduler disabled. Its containers and volume were deleted.

## Characteristics of the verified images

Fleet requires standard Elasticsearch/Kibana authentication and authorization; service
accounts and an encryption key are enabled. The administrator is used only for bootstrap; APM Server
writes as separate `apm_writer`. Kibana takes the package from bundled assets in air-gapped
mode: no external Package Registry is needed. `test output` in APM Server 9.5.6
does not support Elasticsearch output; the healthcheck uses HTTP with the configured
intake token. Actual indexing was additionally verified through an Elasticsearch query.

## Acceptance artifacts

Temporary logs: `/tmp/olympic-apm-gate-final.log`,
`/tmp/olympic-apm-accept.log`, `/tmp/olympic-apm-restart.log`,
`/tmp/olympic-apm-basic.log`, `/tmp/olympic-apm-fresh.log`.
UI screenshots: `/tmp/olympic-apm-kibana-local.png`,
`/tmp/olympic-apm-kibana-docker.png`. Files in `/tmp` are local verification artifacts;
they are not included in delivery and may be deleted by the system.

Acceptance complete: 15/15 tasks. The host test application was stopped; containers,
networks, and volumes of both acceptance Compose projects were deleted. The service role was checked
again: APM Server is ready without authorization errors; read restricted indices permission
is allowed only for the exact name `.apm-agent-configuration`.

## Addendum: SQL spans — 2026-11-11

Added engine-local SQLAlchemy handlers for SQL spans within HTTP and `sync`.
`db.statement` contains sanitized SQL structure with identifiers and placeholders;
parameters are not collected, literals are replaced with `?`, and comments are removed.
Sanitized text is limited to 10000 characters. Verified escape strings, dollar quoting,
nested comments, and unterminated literals. SQL spans end correctly
on errors; concurrent HTTP requests, sampling 0, and disabled APM were checked.
Recording transport confirms `db.statement` contents and absence of test
parameter values, literals, comments, and connection URL from the payload.

Last `./quality-gate.sh` after refinements: Ruff passed, mypy passed (49 files),
pytest **211 passed, 1 deselected**, coverage **94.89%**, `apm.py` — 100%.
The real Compose smoke for the SQL refinement was not rerun; the user confirmed
local application operation and viewing traces in Kibana. Historical results
of the initial Compose smoke are listed above. All 17 implementation tasks complete.
