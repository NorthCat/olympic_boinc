# Proposal

## Why

Functional tests verify API responses but do not show latency and throughput with concurrent clients. A reproducible way to load the REST API and obtain a Locust report is needed before changing queries or server configuration.

## What Changes

- Add a separate set of Locust scenarios for medal standings, the challenge list, challenge and team cards, and `/health`.
- Obtain real identifiers through the API, check HTTP statuses and response structure, and group statistics by scenario.
- Support interactive and headless execution with address, user count, spawn rate, and duration configured through standard Locust parameters; save CSV and HTML reports.
- Describe preparing a populated database through existing CSV import, disabling the scheduler, and a short verification run.
- Add Locust as a separate optional dependency and exclude reports from Git.

## Capabilities

### New Capabilities

- `api-load-testing`: scenarios, response validation, and reproducible execution of REST API load tests.

### Modified Capabilities

None: the existing REST API contract does not change.

## Impact

Planned files: `load_tests/locustfile.py`, `load_tests/README.md`, `pyproject.toml`, `.gitignore`, and a link from `README.md`. Locust runs as a separate process against an already running application. Migrations, production dependencies, and API handlers do not change. Tests use only GET to the specified server and do not contact BoincStats. Target SLAs and automatic load execution in CI are outside this change.
