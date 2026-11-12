# Proposal

## Why

Application logs show errors and synchronization results but do not provide a unified view of HTTP request and background run timing. A self-hosted Elastic APM stack will allow observing the application consistently when running locally and in Docker Compose.

## What Changes

- Add the Elastic APM Python agent with configurable enablement, service name, environment, server address, token, and sampling.
- Record HTTP transactions and unhandled errors, excluding `/health` and static resources; separately track background synchronization runs and their statuses.
- Add SQL spans within HTTP transactions and background synchronization: operation type, duration, outcome, and query text in `db.statement` with preserved table/column names and placeholders. Remove comments and replace string/numeric literals with `?`; do not send parameter values or the connection address.
- Add an `observability` Compose profile with Elasticsearch, Kibana, and standalone APM Server, Elastic authentication and authorization, automatic service account and APM integration setup, and telemetry persistence in a separate volume.
- Support sending from the host to `http://127.0.0.1:8200`, from the container to `http://apm-server:8200`; viewing through `http://127.0.0.1:5601`.
- Preserve regular startup without the stack or mandatory APM availability; the agent is disabled by default, with enablement documented for both execution methods.
- Preserve existing API, web UI, logs, and the “synchronization outside the container” restriction.

## Capabilities

### New Capabilities

- `elastic-apm`: server-side HTTP, SQL, and background synchronization telemetry, configuration, data sanitization, and application independence from APM availability.

### Modified Capabilities

- `container-deployment`: an additional self-hosted Elastic Stack profile available to container and local applications.

## Impact

`pyproject.toml` and `uv.lock` (runtime `elastic-apm`), `config.py`, `api/app.py`, a new APM integration module, `scheduler.py`; configuration and integration tests. `docker-compose.yml`, new stack settings/setup script in `docker/`, `.env.example`, `.docker-env.example`, README, and AGENTS. Database schema and migrations do not change.

The current lock contains FastAPI 0.142.2 and Starlette 1.7.0; Elastic's official table limits the built-in Starlette integration to versions `<1`. The plan uses the public Client API and a small custom ASGI wrapper without downgrading application dependencies. Full browser RUM, collection of all logs, and infrastructure metrics are outside this iteration.
