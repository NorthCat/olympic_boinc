# REST API load tests

Run commands from the repository root. The Locust generator and server run as
separate processes. Python 3.13, PostgreSQL, and a CSV with podium placements are required (see
[data transfer](../README.md#data-transfer-through-csv)). Chrome is not required.

## Preparation

Uses uv and the project lockfile. For an external environment, first export
`UV_PROJECT_ENVIRONMENT` in each terminal (see [installation](../README.md#installation));
without this variable, uv uses `.venv`.

```bash
uv sync --locked --extra load
```

Create a separate database for load testing. In a separate server terminal, set
`OLYMPIC_DATABASE_URL` to its address and credentials (or use the local
`.env`). Do not save secrets in reports or Git. Apply migrations and import
your CSV through the existing CLI:

```bash
uv run --locked --extra load alembic upgrade head
uv run --locked --extra load python -m olympic_boinc.csv_transfer import dumps/import.csv
OLYMPIC_SCHEDULER_ENABLED=false uv run --locked --extra load uvicorn olympic_boinc.api.app:create_app \
    --factory --host 127.0.0.1 --port 8000
```

The `OLYMPIC_DATABASE_URL` variable must point to the same database in all three
commands. The scheduler is disabled: load testing does not trigger synchronization or contact
BoincStats. Do not change data during measurement.

## Running

In the generator terminal:

```bash
uv run --locked --extra load locust -f load_tests/locustfile.py --host http://127.0.0.1:8000
```

Open `http://localhost:8089`, set the number of users and spawn rate.
The target API address is specified through `--host`. Reports are available in the UI.

Short check: one user, spawning one per second, 30 seconds:

```bash
mkdir -p load_tests/reports
uv run --locked --extra load locust -f load_tests/locustfile.py --host http://127.0.0.1:8000 \
    --headless --users 1 --spawn-rate 1 --run-time 30s \
    --csv load_tests/reports/smoke --html load_tests/reports/smoke.html
```

Main example: 20 users, spawning two per second, five minutes:

```bash
uv run --locked --extra load locust -f load_tests/locustfile.py --host http://127.0.0.1:8000 \
    --headless --users 20 --spawn-rate 2 --run-time 5m \
    --csv load_tests/reports/baseline --html load_tests/reports/baseline.html
```

The report directory is excluded from Git. Use different prefixes for different runs.
An HTTP, connection, JSON, or response structure error counts as a failure; headless
execution exits with code 1 on such errors or user exceptions. An empty database
or absence of podium finishers on the initial page stops the user with
a diagnostic and also means an unsuccessful run. The request timeout is 15 seconds;
redirects are not followed.

## Profile and interpretation

Relative task weights: standings 5, list 3, challenge card 2, team
card 2, health 1. Between tasks, a user waits a random 1–3 seconds.
This is a baseline comparison profile rather than a measured model of real traffic.

Standings cycle through no filters, `project`, `team`, and a date period based on
the selected challenges (UTC). The list cycles through the first and last pages
of size 10, the first page of sizes 50 and 200, and types `project` and `team`. In a small database,
the first and last pages may coincide. Each user first loads
up to 200 recent challenges; card IDs are randomly selected only from this
sample and its podium finishers. Arbitrary and nonsequential IDs are supported.
There is no full history traversal. The preparation request is labeled `setup /api/challenges`.

Statistics distinguish filter and page variants, and aggregate IDs as
`/api/challenges/{id}` and `/api/teams/{id}`. Status 200, required
JSON fields and containers, the card ID, and `status=ok` for health are checked; aggregates and sorting
are not recalculated. An empty filter result is allowed.

Smoke checks startup but does not guarantee selection of all random tasks. For
a full run, ensure the report contains all 14 groups (including setup) and that
each group has requests. Ramp-up adds preparation requests: account for this
in analysis. Compare RPS, failure rate, and p50/p95/p99 by operation, as well as
PostgreSQL and server load. Code 0 indicates no detected errors;
there is no agreed latency SLA yet.

For each comparison, save the date, git revision, command,
Python and Locust versions, duration, number of users, spawn rate,
number of challenges and teams (for example, list `total` and the length of the unfiltered
standings), number of IDs in the initial sample, CPU/RAM/OS, PostgreSQL version,
pool and database settings, and number of uvicorn workers alongside the report. Exclude passwords and URLs with credentials.
A generator on the same machine as the server competes for resources; for serious
measurements, run it on another machine and record network parameters.

## Testing the scenario itself

With the `load` extra, controlled HTTP checks run separately:

```bash
uv run --locked --extra load python -m unittest discover -s load_tests -p 'test_*.py' -v
```

They test all variants and errors against a local HTTP server. Regular `pytest`
uses `testpaths = ["tests"]` and does not run load tests.
