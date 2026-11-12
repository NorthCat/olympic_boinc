# Design

## Context

See the motivation in `proposal.md`. The API is implemented in `src/olympic_boinc/api/routers/`, and formats are in `api/schemas.py`. All routes read PostgreSQL; `/health` executes `SELECT 1`. Existing pytest fixtures use rolled-back transactions and are not intended for a separate HTTP server. `csv_transfer import` already exists to prepare persistent data. `pyproject.toml` has a `dev` group; Locust is not yet present.

## Goals / Non-Goals

**Goals:** separate the load generator from the server, measure real HTTP requests and SQL against prepared data, and obtain commands for repeatable runs.

**Non-Goals:** load on the scraper and BoincStats, a synthetic data generator, changing SQL or the connection pool, automatic SLAs, load execution in regular pytest or CI. Distributed execution is outside the initial verification.

## Decisions

### Separate dependency and directory

Add optional extra `load` with Locust, scenario `load_tests/locustfile.py`, and instructions `load_tests/README.md`. Verify the selected version's Python 3.13 compatibility during implementation. The generator runs as a separate process; it needs no application, SQLAlchemy, or server settings imports. The alternative — inclusion in `dev` — increases mandatory installation for developers who do not need load testing.

### Mixed profile

One HTTP user with a 1–3 second pause between tasks. Relative weights: standings 5, list 3, challenge card 2, team card 2, health 1. This is an initial comparison profile rather than a claim about real traffic. Standings variants cycle through no filters, `project`, `team`, and a period; list variants cycle through the first and last available page at `size=10`, the first at `size=50` and `size=200`, and both type filters. The period comes from the dates of obtained challenges; pages are calculated from `total` to avoid relying on a large database.

Standard Locust parameters specify `--host`, `--users`, `--spawn-rate`, `--run-time`, `--headless`, `--csv`, `--html`. A custom LoadTestShape and configuration layer are not yet needed. Statistics names identify the request variant; dynamic IDs are replaced with `{id}`. Set a finite HTTP timeout so a stalled server counts as an error.

### Preparing each user through the API

Initially, fetch the first page of up to 200 challenges and collect bounded sets of challenge IDs and `placements[].team_id`, along with dates and `total`. Store them in user memory and select cards from these sets. Initial requests have a separate statistics name. This limits the sample to recent challenges but requires no full database traversal and works with arbitrary IDs. Alternatives: hardcoded IDs are unreliable, and generator access to PostgreSQL couples it to the internal schema.

Invalid preparation is recorded as a failed request; the user stops with a clear diagnostic. The exit handler preserves a nonzero exit code on errors, including an empty sample, even if the HTTP status was 200. Standard failure tracking and an explicit preparation error flag are sufficient for the first version; do not introduce separate custom p95 thresholds.

### Response validation

Use `catch_response` for status and minimal JSON structure: a list of medal rows with required fields; a page object with `items`, `total`, `page`, `size` and challenge and podium finisher structure; cards with required fields and the requested ID; health with status `ok`. An empty filtered list is allowed; an empty initial sample is a preparation error. Do not recalculate aggregates and sorting on each request: this is already covered by functional tests and would add work to the load generator. Validation runs locally in the scenario without importing application models.

### Data population and reports

Instructions use a dedicated database with applied migrations and the existing CSV import. During a run, the application starts with `OLYMPIC_SCHEDULER_ENABLED=false`. No separate seed script or new migrations. Reports are saved in `load_tests/reports/`, a directory ignored by Git. Document RPS, failures, and percentiles, recording challenge and team counts, machine configuration, uvicorn worker count, application/database settings, generator parameters and version.

## Risks / Trade-offs

- Generator and server load on one machine distorts results → state this in the instructions and recommend a separate machine for serious measurements.
- Sampling only the first 200 challenges limits card diversity → explicitly describe the limitation and data volume used in the run report.
- Starting each user adds a list request → a separate statistics name, gradual user spawning, and accounting for ramp-up in analysis.
- A short run does not guarantee all randomly selected tasks execute → verify each scenario separately and perform a main run of sufficient duration.
- Without agreed SLAs, a report does not prove suitability for a given traffic volume → evaluate the baseline, using a nonzero exit code for correctness errors rather than arbitrary latencies.

## Migration Plan

No schema or server deployment changes are needed. Install `.[load]`, prepare data, perform verification and main runs. To roll back, remove the extra, scenario directory, and instruction links; API data do not change.
