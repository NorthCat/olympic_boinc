# Olympic BOINC

Olympic-style BOINC team medal standings with a web interface and a read-only REST API. Once a day, the service fetches completed team challenges from [BoincStats](https://www.boincstats.com) — project challenges (`/stats/pchallenge/team/overview`) and team challenges (`/stats/challenge/team/overview`) — saves podium finishers, and awards gold, silver, and bronze for 1st, 2nd, and 3rd places.

Browse the [web interface](#web-ui) at `/` with year and challenge type filters and an English/Russian language selector (English by default). The [REST API](#rest-api) provides standings, challenge results, and team details; interactive API documentation is available at `/docs`. Both are served by the same application, locally or in Docker.

## How it works

```
BoincStats ──► scraper (Chrome + HTML parsing) ──► sync ──► PostgreSQL ──► REST API
                         ▲
                 scheduler (cron, once a day)

REST API ◄── web interface (browser) / API clients
```

- **Fetching.** BoincStats is protected by Cloudflare, so pages are fetched by a real Chrome browser through [nodriver](https://github.com/ultrafunkamsterdam/nodriver). The browser runs only for the duration of synchronization.
- **Synchronization.** On each run:
  1. both challenge lists are fetched;
  2. completed challenges not yet in the database are selected, newest first;
  3. their pages are fetched, up to `OLYMPIC_SYNC_MAX_CHALLENGES` per run;
  4. teams that took places 1–3 are saved.
- **What is not fetched again.** Already saved challenges are neither fetched nor changed. Challenges without results are not saved and are checked again on the next run.
- **CAPTCHA protection.** BoincStats shows a CAPTCHA when requests are too frequent, so there is a delay between requests (`OLYMPIC_REQUEST_DELAY`). The entire history, around 1070 challenges, is loaded over several daily runs, with recent challenges first.
- **Teams.** A team is identified by its name exactly as shown by BoincStats. Ties are allowed: two teams in 2nd place each receive silver.
- **Web interface.** The browser page uses the REST API to display medal standings and update year/type filters without reloading. HTML, CSS, and JavaScript are included in the application package; no separate frontend server is needed.
- **Log.** Each run summary is written to the application log; run history is not stored in the database.

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (migration verified with 0.13.7); Python 3.13 is specified in `.python-version`
- PostgreSQL 18: locally or through `docker compose`
- Chrome or Chromium. The browser runs with a window, so a server without a display needs Xvfb (`xvfb-run`).

## Installation

```bash
uv python install
uv sync --locked
cp .env.example .env    # fill in the settings, see “Settings”
```

Dependencies are pinned in `uv.lock`; `uv sync --locked` installs the application
and the `dev` group. By default, the environment is created in `.venv`; activation is not required.
For an existing external environment, set the variable **before** all uv commands and
the quality gate in each terminal:

```bash
export UV_PROJECT_ENVIRONMENT=<path_to_env>
uv sync --locked
```


### Database

Option 1 — local PostgreSQL 18 (port 5432):

```sql
CREATE ROLE olympic LOGIN PASSWORD '...' CREATEDB;   -- tests require CREATEDB
CREATE DATABASE olympic_boinc OWNER olympic;
```

Option 2 — database only in Docker (port **5433**): create `.docker-env` from `.docker-env.example` and set `POSTGRES_USER` and `POSTGRES_PASSWORD` in it, then

```bash
docker compose up -d db
```

set `OLYMPIC_DATABASE_URL` in `.env` to use `localhost:5433` and the same credentials. To run the application in Docker too, see “Running in Docker”.

Then apply migrations:

```bash
uv run --locked alembic upgrade head
```

### Data transfer through CSV

Collected challenges can be exported to a CSV file and imported into another database without fetching them from BoincStats again. The connection is taken from `OLYMPIC_DATABASE_URL`.

```bash
uv run --locked python -m olympic_boinc.csv_transfer export                # -> dumps/olympic_boinc_<UTC time>.csv
uv run --locked python -m olympic_boinc.csv_transfer export results.csv    # to the specified file
uv run --locked python -m olympic_boinc.csv_transfer import dumps/olympic_boinc_20261027_120000.csv
```

One file row represents one podium placement; the file contains no internal database IDs. Columns:

| Column | Value |
|---|---|
| `challenge_type` | `project` or `team` |
| `challenge_name` | challenge name |
| `project_name` | BOINC project, empty if unknown |
| `start_at`, `end_at` | ISO 8601, UTC on export; a date without a time zone is treated as UTC on import |
| `url` | challenge link, used to determine whether challenges are the same |
| `team` | team name exactly as on BoincStats |
| `place` | 1–3 |
| `score` | score (integer), empty if unknown |

Import adds only challenges not yet in the database. Already saved challenges are skipped without changes, so importing the same file again creates no duplicates. Teams are matched by exact name. The entire file is validated first: if there is even one error, nothing is imported, and all errors are printed with line numbers (exit code 1). If the file was edited in Excel or LibreOffice, save it as “CSV UTF-8” with a comma delimiter.

## Settings

All settings are environment variables with the `OLYMPIC_` prefix and can be set in `.env`. The full list with comments is in [`.env.example`](.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `OLYMPIC_DATABASE_URL` | — (required) | `postgresql+asyncpg://user:password@host:port/olympic_boinc` |
| `OLYMPIC_SYNC_CRON` | `0 3 * * *` | Synchronization schedule, cron in UTC |
| `OLYMPIC_SCHEDULER_ENABLED` | `true` | `false` — the API runs, synchronization does not start |
| `OLYMPIC_SYNC_ON_STARTUP` | `false` | `true` — run synchronization immediately on startup, then on schedule |
| `OLYMPIC_SYNC_MAX_CHALLENGES` | `100` | Number of challenge pages to fetch per run |
| `OLYMPIC_SYNC_LOG_FILE` | `logs/sync.log` | Synchronization run log, relative to the working directory (see “Logs”) |
| `OLYMPIC_REQUEST_DELAY` | `60` | Delay between requests to BoincStats, in seconds |
| `OLYMPIC_REQUEST_RETRIES` | `3` | Retries on network errors, 5xx, and 429 |
| `OLYMPIC_BROWSER_PATH` | autodetect | Path to Chrome/Chromium |
| `OLYMPIC_BROWSER_SANDBOX` | `true` | `false` for Chromium without an AppArmor profile (for example, Playwright's Chromium) |
| `OLYMPIC_TEST_DATABASE_URL` | — | PostgreSQL server for tests (see “Tests”) |

Do not reduce `OLYMPIC_REQUEST_DELAY` for full runs: frequent requests cause BoincStats to show a CAPTCHA and interrupt the run.

## Running

```bash
uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

On a server without a display:

```bash
xvfb-run uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

The scheduler starts and stops with the application. Synchronization runs do not overlap: if the previous run is still in progress, the next scheduled run is skipped.

By default, synchronization **does not run** on application startup: the first run occurs at the next time specified by `OLYMPIC_SYNC_CRON`. To run it immediately, set `OLYMPIC_SYNC_ON_STARTUP=true`. The first run then starts on startup, and subsequent runs follow the schedule. The startup run follows the same rules: it does not overlap with a scheduled run, is logged, and closes the browser. The setting has no effect unless the scheduler is enabled.

Enable it for the first deployment or verification, but do not keep it enabled where the application restarts frequently (debugging, `Restart=on-failure` for an unstable service). Each restart means another traversal of the site, and frequent requests lead to a BoincStats CAPTCHA.

If running multiple application instances, leave `OLYMPIC_SCHEDULER_ENABLED=true` on only one. Concurrent runs will not corrupt data, but will double requests to the site.

**Quick check that everything works** (synchronization immediately on startup, 3 challenges per run):

```bash
OLYMPIC_SYNC_ON_STARTUP=true OLYMPIC_SYNC_MAX_CHALLENGES=3 \
  uv run --locked uvicorn olympic_boinc.api.app:create_app --factory
```

After a few minutes (depending on the delay between requests), a summary appears in the log:

```
INFO olympic_boinc.sync: sync ok in 13 s: added=2 skipped=1 deferred=1062 errors=0
```

- `added` — new challenges saved;
- `skipped` — without results or with an error, to be checked next time;
- `deferred` — not fetched because of the limit, waiting for subsequent runs.

Statuses:
- `ok` — no errors;
- `partial` — errors in individual challenges, or a run interrupted by a CAPTCHA;
- `failed` — the challenge list could not be fetched.

There is no manual synchronization trigger (CLI or HTTP); only the scheduler starts synchronization: on schedule and, if `OLYMPIC_SYNC_ON_STARTUP` is enabled, on startup.

## Logs

All application and uvicorn logs go to **stderr**.

### Synchronization log

If the scheduler is enabled, everything related to synchronization is also written to **`logs/sync.log`** in the working directory, meaning the project root for a regular run. The directory is created automatically. The path is changed through `OLYMPIC_SYNC_LOG_FILE` and can also be absolute.

The log contains:
- scheduler start and stop;
- run start (`sync job started`);
- every request to BoincStats (`GET <url>`, retries on separate lines);
- challenge errors with tracebacks;
- run summary (`sync ok|partial|failed ...`).

The log contains no REST API logs. The file rotates at 10 MB, retaining 5 archive files (`sync.log.1` … `sync.log.5`).

Example of a run interrupted by a CAPTCHA:

```
2026-10-27 03:00:00,001 INFO apscheduler.executors.default: Running job "sync (trigger: cron[...], next run at: ...)" (scheduled at 2026-10-27 03:00:00+00:00)
2026-10-27 03:00:00,002 INFO olympic_boinc.scheduler: sync job started
2026-10-27 03:00:00,010 INFO olympic_boinc.scraper.fetcher: GET https://www.boincstats.com/stats/pchallenge/team/overview
2026-10-27 03:02:10,011 INFO olympic_boinc.scraper.fetcher: GET https://www.boincstats.com/stats/challenge/team/overview
...
2026-10-27 03:41:10,415 ERROR olympic_boinc.sync: https://www.boincstats.com/stats/pchallenge/team/list/42080/rank: BlockedError: status=200: BoincStats captcha (too many requests)
2026-10-27 03:41:10,416 WARNING olympic_boinc.sync: sync partial in 2470 s: added=17 skipped=2 deferred=1041 errors=1
```

The number of requests in a run is the number of `GET` lines between `sync job started` and the summary:

```bash
grep -c "GET https://" logs/sync.log            # total requests in the log
grep "olympic_boinc.sync: sync " logs/sync.log  # run summaries
```

### Full application output

To save all output during a manual run, redirect it:

```bash
# to the terminal and a file
uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000 2>&1 | tee -a app.log

# to a file only, in the background
nohup uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000 >> app.log 2>&1 &
```

Loggers:

- `olympic_boinc.sync` — summary of each run and errors for individual challenges, with tracebacks. Summary line level: `INFO` for `ok`, `WARNING` for `partial`, `ERROR` for `failed`.
- `olympic_boinc.scraper.fetcher` — every request to the site, retries, clicks on the Cloudflare check.
- `apscheduler` — scheduler start and stop, job execution, skipping a run if the previous one is still in progress (`maximum number of running instances reached`).

“Job ... executed successfully” from APScheduler only means that the job did not crash. Check the synchronization result in the `olympic_boinc.sync: sync ...` line: a run interrupted by a CAPTCHA also finishes “successfully” from the scheduler's perspective.


## Running in Docker

Docker Compose starts the database and REST API. The image is built by uv 0.13.7 from `uv.lock`
with runtime dependencies, without dev/load. The container uses `/app/.venv`; the local
`UV_PROJECT_ENVIRONMENT` is not passed to it, and packages are not installed on startup. Python does not need to be installed on the server. Building and running require Docker with Compose v2 and access to it: the `docker` group (`sudo usermod -aG docker $USER`, then log in again) or `sudo`.

**There is no synchronization in the container.** Chromium in the container does not pass the Cloudflare check on BoincStats, so the scheduler is always disabled in the container, even if settings specify `OLYMPIC_SCHEDULER_ENABLED=true`. Data reach the container from a CSV file on startup or from synchronization running outside the container (see below).

1. For a new environment, create `.docker-env` from the provided
   [`.docker-env.example` template](.docker-env.example):

   ```bash
   cp .docker-env.example .docker-env
   ```

   The template already specifies the database/user name, CSV path, and APM connection settings
   inside Docker. Replace the `<...>` placeholders with your own values:

   - `POSTGRES_USER` and `POSTGRES_PASSWORD` — credentials for the database in the container;
   - `OLYMPIC_DATABASE_URL` — database address for the application: host `db`, the same user and password. Special characters in the password are URL-encoded: `@` → `%40`, `/` → `%2F`, `:` → `%3A`, `%` → `%25`, `#` → `%23`.

   You can run `openssl rand -hex 32` separately for each password.
   The resulting hex passwords do not need URL encoding. If running the
   `observability` profile, also replace the `ELASTIC_PASSWORD`,
   `KIBANA_SYSTEM_PASSWORD`, and `APM_WRITER_PASSWORD` placeholders with three different passwords,
   and `KIBANA_ENCRYPTION_KEY` with a separate string of at least 32 characters.
   These four settings are not used for regular db + app startup.

   When configuring an already running environment, edit the existing `.docker-env`,
   preserving its passwords and Kibana key.

   If the passwords in `POSTGRES_PASSWORD` and the URL differ, the application will not connect to the database and will fail during migrations (`docker compose logs app`).

   Containers (both the database and application) read only `.docker-env`. They do not use `.env`, which is needed for execution outside Docker. Without `.docker-env`, compose fails with `env file .../.docker-env not found`.
2. Put the data export in `dumps/import.csv` (see below for how to obtain it).
   The template explicitly sets `IMPORT_FILE=dumps/import.csv`; for another export,
   specify its path, for example `IMPORT_FILE=dumps/results.csv`. It is relative
   to `/app` in the container; the `dumps/` directory is mounted from the host.
3. Build and start:

   ```bash
   docker compose config --quiet
   docker compose up -d --build
   docker compose ps          # app should become healthy
   curl localhost:8000/health
   ```

   To start the entire stack with APM, set
   `OLYMPIC_APM_ENABLED=true` in `.docker-env` and use:

   ```bash
   docker compose --profile observability config --quiet
   docker compose --profile observability up -d --build
   docker compose --profile observability ps -a
   ```

   APM is explicitly disabled (`false`) in the template; starting the profile alone does not enable
   the application agent. The address `http://apm-server:8200` and environment `docker` are already configured.
   Viewing events and logging in to Kibana are described in “Elastic APM”.

On every startup, the container:
1. applies migrations;
2. imports `dumps/import.csv` if the file exists;
3. starts the API.

Import adds only challenges not yet in the database, so the file can be left in place: subsequent startups log `added 0, skipped N`. If the file does not exist, import is skipped.

If the file contains an error, the container does not start the API and exits. Because of `restart: unless-stopped`, it keeps restarting: `docker compose ps` shows `Restarting`. Errors with line numbers are visible in `docker compose logs app`. Fix or remove the file, and the container will start on the next restart. The container behaves the same way if migrations fail.

Parameters:
- the API port on the host is 8000. Set another port through a shell variable on startup, for example `APP_PORT=8080 docker compose up -d`. This is a Compose setting rather than a container setting, so it does not work in `.docker-env`;
- `IMPORT_FILE` in `.docker-env` — another file to import on startup, with a path relative to `/app`, for example `dumps/2026-10.csv`;
- if your user's UID is not 1000 (`id -u`), build the image with `docker compose build --build-arg UID=$(id -u)`, or the container will not be able to write to `dumps/`;
- database data reside in the `pgdata` volume and survive `docker compose down`. Only `docker compose down -v` deletes them.

Application output: `docker compose logs -f app`.

## Elastic APM

APM is disabled by default. The agent records HTTP transactions by route template,
unhandled errors, and background `sync` runs with status and counters.
`/health` and `/static/` are excluded. Request bodies, headers, and local variables
are not sent. Delivery runs in the background; APM unavailability does not stop the API
or synchronization. SQLAlchemy queries within HTTP transactions and `sync` receive
spans of type `db.postgresql.query`: operation type (for example, `SELECT`), duration,
and outcome. Span details provide SQL (`db.statement`) with table names,
column names, and parameter placeholders. String and numeric literals are replaced
with `?`, and comments are removed; parameter values and the connection address are not sent.
Restart the application and open an SQL span from a new trace in Kibana
to see the query text; old traces will not change.
Browser spans and central agent configuration are not enabled in this implementation.

The self-hosted stack runs through the `observability` profile: Elasticsearch, Kibana, and
APM Server **9.5.6**, APM integration **9.5.6**, Python agent **6.26.2** in `uv.lock`.
Docker Compose v2, around 6 GB of free RAM, and space for telemetry are required.
For Elasticsearch on Linux, check `sysctl vm.max_map_count` (at least 262144).
The first startup with integration installation may take several minutes.

In `.docker-env`, fill in `ELASTIC_PASSWORD`, `KIBANA_SYSTEM_PASSWORD`,
and `APM_WRITER_PASSWORD` with different passwords and `KIBANA_ENCRYPTION_KEY` with a string of at least
32 characters (for example, values can be obtained through `openssl rand -hex 32`).
Keep the key across restarts. `elastic-setup` prepares service
accounts, then `apm-setup` installs the bundled integration through the Kibana API
without an external Package Registry. Requests use HTTP(S), without automatic redirects. URLs with credentials,
a query string, or a fragment are rejected before connecting. Installation is confirmed
by a regular status check that also works when running Python with `-O`.
Both steps can be safely repeated; errors produce
a nonzero exit code. With esdata preserved, changing `ELASTIC_PASSWORD` in the file
alone does not change the Elasticsearch user's password.

For the application in Docker, set the following in `.docker-env`:

```dotenv
OLYMPIC_APM_ENABLED=true
OLYMPIC_APM_SERVER_URL=http://apm-server:8200
OLYMPIC_APM_SERVICE_NAME=olympic-boinc
OLYMPIC_APM_ENVIRONMENT=docker
OLYMPIC_APM_TRANSACTION_SAMPLE_RATE=1.0
```

```bash
docker compose --profile observability up -d --build
docker compose --profile observability ps -a
docker compose --profile observability logs apm-server apm-setup elastic-setup
```

The scheduler in the container remains disabled. The application depends only on the database;
regular `docker compose up -d --build` does not start Elastic Stack.

For the application on the host, start only the stack (the application database remains the same):

```bash
docker compose --profile observability up -d --build elasticsearch kibana apm-setup apm-server
```

In the local `.env`, enable `OLYMPIC_APM_ENABLED=true`, set
`OLYMPIC_APM_SERVER_URL=http://127.0.0.1:8200` and `OLYMPIC_APM_ENVIRONMENT=local`.
Start the application with the usual command:

```bash
uv run --locked uvicorn olympic_boinc.api.app:create_app --factory
```

If needed, set `OLYMPIC_APM_SECRET_TOKEN` in `.docker-env` and **the same
value** in `.env`. Without a token, intake does not require authentication. Do not set
`ELASTIC_APM_*` alongside these settings: the Python agent has its own precedence for those variables.
Sampling accepts values from 0 to 1; leave it at 1 for verification.

Open `http://127.0.0.1:5601`, log in as `elastic` with `ELASTIC_PASSWORD`,
go to Observability → APM / Applications, and select `olympic-boinc` and
environment `local` or `docker`. Make a few requests to `/` and `/api/medals`;
events usually appear within a few seconds. The background `sync` transaction
appears after the local scheduler runs. Kibana and intake are published
only on loopback (5601 and 8200); Elasticsearch is not published externally. The
local Docker network uses HTTP; remote access requires a separate
TLS proxy or tunnel.

`docker compose --profile observability down` preserves telemetry in a separate
`esdata` volume. To disable observability, set `OLYMPIC_APM_ENABLED=false`
and stop the profile services. To delete **only telemetry**, first stop
the stack, then find the exact volume name and delete only that volume:

```bash
docker compose --profile observability down
docker volume ls --filter label=com.docker.compose.volume=esdata
docker volume rm <exact-esdata-volume-name-for-this-project>
```

Do not use `down -v` for this operation: it also deletes PostgreSQL `pgdata`.
The quality gate tests the agent without an external Elastic Stack; real delivery
scenarios are described in the OpenSpec change `elastic-apm-observability`.

### How data reach the container

Synchronization runs outside the container, where Cloudflare allows it: on your machine or on a server without Docker (see “Running”, “Running through systemd”). There are two ways to transfer data to the container.

**Through CSV** — suitable if synchronization runs on another machine:

```bash
uv run --locked python -m olympic_boinc.csv_transfer export dumps/import.csv     # where synchronization runs
# copy the file to dumps/import.csv next to docker-compose.yml, then
docker compose restart app                                        # import on startup
# or without restarting:
docker compose exec app python -m olympic_boinc.csv_transfer import dumps/import.csv
```

Export from the container: `docker compose exec app python -m olympic_boinc.csv_transfer export`. The file appears in `dumps/` on the host.

**Directly to the container database** — if synchronization runs on the same machine. The container database is accessible on the host through port 5433. Run the application outside the container (with the scheduler, as usual) with this database address:

```bash
OLYMPIC_DATABASE_URL=postgresql+asyncpg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@localhost:5433/olympic_boinc \
    xvfb-run uv run --locked uvicorn olympic_boinc.api.app:create_app --factory --port 8001
```

New challenges are immediately visible in the container API. Port 5433 must not be accessible from the internet: close it with a firewall or publish it only on the local address (`"127.0.0.1:5433:5432"` in `docker-compose.yml`).

Updating: `git pull`, then `docker compose up -d --build`.

If `POSTGRES_USER`/`POSTGRES_PASSWORD` were previously set in `.env`, move them to `.docker-env` (with the same values: the `pgdata` volume was created with them) and add `OLYMPIC_DATABASE_URL`. They can be removed from `.env`. Run `docker compose build --pull` occasionally to update the base image.

## Web UI

After startup, open `http://localhost:8000/` (in Docker, port `APP_PORT`, default 8000).
The page shows team medal standings: gold, silver, bronze, and total medals.
The interface defaults to English. The header selector offers English and Русский;
an explicit choice is remembered in browser storage when available. Switching languages
updates all interface text without resetting the year/type filters or reloading data.
Team names remain exactly as provided by BoincStats.
Two filters apply immediately, without reloading:

- **Year:** “All time” or the challenge end year in UTC. The list is built
  from data when the page opens, from newest to oldest, and is shared by both types.
- **Challenge type:** “All types”, “Team”, “Project”.

The order is Olympic: gold first, then silver and bronze, with team name breaking ties.
If there are no medals for the combination, the page reports this; a failed load can be
retried with the “Retry” button. JavaScript is required.

The UI consists of local HTML/CSS/JavaScript in `src/olympic_boinc/web/static/`.
It is included in the Python package and Docker image; no separate frontend server, npm, or CDN is needed.
The Python quality gate does not measure JavaScript: filter behavior and responsiveness
need additional browser verification when changing the UI.

## REST API

OpenAPI documentation: `http://localhost:8000/docs` (schema: `/openapi.json`). The API is read-only.

| Method and path | Returns |
|---|---|
| `GET /api/medals` | Medal standings |
| `GET /api/challenges` | Challenges with podium finishers, paginated |
| `GET /api/challenges/years` | Unique end years of all challenges in UTC, descending; `[]` for an empty database |
| `GET /api/challenges/{id}` | One challenge with podium finishers |
| `GET /api/teams/{id}` | Team medals and challenges in which it earned a podium placement |
| `GET /health` | `200 {"status": "ok"}` or `503` if the database is unavailable |

### Medal standings

Sorting: by gold, then silver, then bronze, all descending. When all are equal, by team name.

Parameters:
- `challenge_type` — `project`, `team`, or `all` (default `all`);
- `from`, `to` — dates in `YYYY-MM-DD` format, both inclusive. The filter uses the challenge end date in UTC.

If a parameter is invalid, the response is 422.

```bash
curl 'localhost:8000/api/medals?challenge_type=project&from=2026-01-01&to=2026-12-31'
```

```json
[
  {"team_id": 1, "team_name": "The FPS Team", "gold": 4, "silver": 0, "bronze": 0, "total": 4},
  {"team_id": 2, "team_name": "Czech National Team", "gold": 0, "silver": 3, "bronze": 1, "total": 4}
]
```

### Challenges

Parameters:
- `challenge_type` — as for medal standings;
- `page` — page number, starting at 1;
- `size` — page size, default 50, maximum 200.

Sorted by end date, newest first.

```bash
curl 'localhost:8000/api/challenges?page=1&size=10'
```

```json
{
  "items": [
    {
      "id": 1,
      "challenge_type": "project",
      "name": "Suzuki's Birthday Challenge",
      "project_name": "PrimeGrid",
      "start_at": "2026-10-02T17:00:00Z",
      "end_at": "2026-10-07T17:00:00Z",
      "url": "https://www.boincstats.com/stats/pchallenge/team/list/42109/rank",
      "placements": [
        {"team_id": 1, "team_name": "The FPS Team", "place": 1, "score": 348043392},
        {"team_id": 2, "team_name": "Czech National Team", "place": 2, "score": 334315680},
        {"team_id": 3, "team_name": "SETI.Germany", "place": 3, "score": 284077760}
      ]
    }
  ],
  "total": 4,
  "page": 1,
  "size": 10
}
```

### Team

```bash
curl localhost:8000/api/teams/1
```

The response contains `id`, `name`, `gold`, `silver`, `bronze`, `total`, and `challenges` — challenges in which the team earned a podium placement, with a `place` field. If the team does not exist, the response is 404.

## Tests

```bash
uv run --locked pytest                      # all tests, without contacting the site
uv run --locked pytest tests/test_api.py    # one file
uv run --locked pytest -m live              # smoke tests against real BoincStats (requires a browser)

# Run with code coverage analysis
uv run --locked pytest \
  --cov=olympic_boinc \
  --cov-report=term-missing \
  --cov-report=html
```

Tests require PostgreSQL:
- if `OLYMPIC_TEST_DATABASE_URL` is set, each run creates its own database `<name>_<random suffix>` on that server and drops it at the end, so runs can execute in parallel;
- otherwise, a `postgres:18` container starts through testcontainers; Docker is required.

Full quality gate: Ruff, mypy, pytest with line coverage of at least **90%**,
Bandit, pip-audit, and Semgrep:

```bash
./quality-gate.sh
```

GitHub Actions runs the same script on every push, in pull requests, and manually
through Actions → Quality gate → Run workflow. The workflow is in
[`.github/workflows/quality-gate.yml`](.github/workflows/quality-gate.yml): Ubuntu 24.04,
Python from `.python-version`, uv 0.13.7 with caching, and a separate PostgreSQL 18.
Semgrep is installed in a separate environment through `uv tool install`.
Tests create and drop their own database; credentials specified in the workflow apply
only to the temporary CI service, and GitHub Secrets are not needed to run it.
Live tests are excluded by the standard pytest configuration. An outdated run for the same
branch or pull request is canceled when a new one arrives. To prevent merging
on failures, make the `Quality gate` check required in the target branch ruleset.

Ruff checks lint/import ordering, line length (100 characters), and formatting
through `ruff format --check`. To apply formatting, use
`uv run --locked --no-sync ruff format .`. Logical blocks inside functions
are separated by blank lines according to `AGENTS.md`; this is checked in code review.

The script installs the `dev` and `security` groups and the `load` extra from the lockfile
and inherits `UV_PROJECT_ENVIRONMENT`. Bandit and pip-audit run through uv.
Semgrep is installed separately and must be available as `semgrep` on the `PATH`
of the terminal or PyCharm Run Configuration; it is not a project dependency.
All six checks run even if one fails; an environment preparation error
stops the gate immediately. Missing Semgrep, findings, and scanner errors produce a nonzero
final code; checks are not silently skipped.

Bandit checks Python code in the application, migrations, scripts, Docker bootstrap, and
load scenarios (`src`, `migrations`, `scripts`, `docker`, `load_tests`).
pip-audit checks runtime/dev/security/load dependencies pinned in `uv.lock`:
the gate temporarily exports them with hashes without the local project package and checks them without resolving
dependencies again or installing packages. The temporary file is removed on exit.
Semgrep scans the same directories, `tests`, `Dockerfile`, and the quality gate with the
`p/security-audit` ruleset; findings and errors count as failures (`--error --strict`).
The `.semgrepignore` file keeps tests in scope, excluding only support
and generated files; `--no-git-ignore` allows new code to be checked before commit.
pip-audit needs access to the vulnerability database, and Semgrep to the rules registry;
the remote ruleset and vulnerability database may change between runs.

Fetching and parsing tests use saved BoincStats HTML pages from `tests/fixtures/`. Fixtures can be updated with `uv run --locked python scripts/spike_fetch.py --save DIR [URL ...]`.

REST API load tests with Locust: [preparation and execution](load_tests/README.md).

## Common problems

- **`could not find a valid chrome browser binary`** — specify `OLYMPIC_BROWSER_PATH`. For Chromium not installed from a .deb (for example, from Playwright), also add `OLYMPIC_BROWSER_SANDBOX=false`.
- **`BlockedError` in the log and status `partial` or `failed`** — BoincStats displayed a CAPTCHA or Cloudflare check. Ensure `OLYMPIC_REQUEST_DELAY` is not too low. The next run will continue from the same point.
- **`added=0`, while `skipped` grows from run to run** — many challenges without results occupy the entire run limit. Increase `OLYMPIC_SYNC_MAX_CHALLENGES`.
- **BoincStats corrected the results of an already saved challenge** — saved challenges are not updated. Delete the challenge from the `challenge` table, and the next run will fetch it again.

## Development

Dependencies change together with `uv.lock`:

```bash
uv add <package>                  # runtime
uv add --dev <package>            # development tools
uv add --optional load <package>  # load testing tools
uv remove <package>
uv lock --check                   # check manifest and lock consistency
```

After changing the manifest, run `uv lock` and commit `pyproject.toml` and
`uv.lock` together. For regular installation and execution, use `--locked` so that
an outdated lockfile causes an error rather than changing silently.

Migrations:

```bash
uv run --locked alembic revision --autogenerate -m "..."   # new migration
uv run --locked alembic check                              # model schema matches migrations
```

Changes are managed through [OpenSpec](https://github.com/Fission-AI/OpenSpec):
- `openspec/specs/` — current specifications;
- `openspec/changes/` — changes in progress;
- `openspec/changes/archive/` — completed changes.

Code architecture details are in [`AGENTS.md`](AGENTS.md).
