# AGENTS.md

This file provides guidance to Codex when working with code in this repository.

## Project

Backend that scrapes completed team challenges from BoincStats (project challenges and team-organised challenges) once a day and serves Olympic-style medal standings (gold/silver/bronze = 1st/2nd/3rd place) over REST. Work is split into OpenSpec changes, applied in order: `project-foundation` → `boincstats-fetching` → `challenge-parsing` → `challenge-sync` → `scheduled-sync` / `medals-rest-api`.

## Commands

Use uv project commands from the repository root (`uv run --locked ...`); Python is pinned in `.python-version`, dependencies in `uv.lock`. The default environment is `.venv`. For this machine, export `UV_PROJECT_ENVIRONMENT=/home/mikhail/venvs/olympic_boinc_uv` before uv commands and the quality gate; do not hardcode this path in scripts or pyproject. Activation alone does not select an external environment for uv.

- Install: `uv sync --locked` (dev group included); add `--extra load` for Locust and `--group security` for Bandit/pip-audit. The full quality gate uses both; Semgrep must be installed separately on PATH.
- Config: copy `.env.example` to `.env`; every setting is an `OLYMPIC_*` env var (see `src/olympic_boinc/config.py`).
- Database: local PostgreSQL 18 on `localhost:5432`, credentials only in `.env` (never commit them; the role needs `CREATEDB` for tests), dev DB `olympic_boinc`. Alternative: `docker compose up -d db` (port 5433; needs docker group membership and `POSTGRES_USER`/`POSTGRES_PASSWORD` in `.docker-env`); the whole app in Docker: see Docker below.
- Migrations: `uv run --locked alembic upgrade head`; new migration: `uv run --locked alembic revision --autogenerate -m "..."`; drift check: `uv run --locked alembic check`. The URL comes from settings, not `alembic.ini`. Downgrades must also drop PostgreSQL enum types.
- CSV transfer: `uv run --locked python -m olympic_boinc.csv_transfer export [FILE]` / `import FILE` (export defaults to `dumps/olympic_boinc_<UTC time>.csv`, gitignored; see `csv_transfer.py`).
- Docker: `docker compose up -d --build` runs `db` + `app` (web UI + API, no sync in the container, Chromium there does not pass BoincStats' Cloudflare check; `OLYMPIC_SCHEDULER_ENABLED=false` is forced). `Dockerfile`: python:3.13-slim, uv 0.13.7 installs runtime dependencies from `uv.lock` into `/app/.venv` without dev/load extras; its bin directory is on PATH, no browser, non-root user (`--build-arg UID`). `docker/entrypoint.sh`: `alembic upgrade head` → `csv_transfer import $IMPORT_FILE` if the file exists (default `dumps/import.csv`, set in the entrypoint; an error stops the container) → `exec uvicorn`. Both services read `.docker-env` (`env_file`, required; template `.docker-env.example`; `.env` is only for running outside Docker): `POSTGRES_*`, an explicit `OLYMPIC_DATABASE_URL` with host `db`, `IMPORT_FILE`; compose forces `OLYMPIC_SCHEDULER_ENABLED=false` over it; `./dumps` is mounted (kept in git via `.gitkeep`); API on `${APP_PORT:-8000}` (a shell variable, compose substitution). Data gets in by the startup CSV import, `docker compose exec app python -m olympic_boinc.csv_transfer ...`, or a sync run outside the container against `localhost:5433`.
- Run the server: `uv run --locked uvicorn olympic_boinc.api.app:create_app --factory` (web UI at `/`, OpenAPI docs at `/docs`). The scheduler runs the sync on `OLYMPIC_SYNC_CRON` (UTC, default `0 3 * * *`); `OLYMPIC_SCHEDULER_ENABLED=false` turns it off; `OLYMPIC_SYNC_ON_STARTUP=true` also runs it right after startup (the same job, first due now). Each run opens Chrome via nodriver with a window, so a server needs a display: `xvfb-run uv run --locked uvicorn ...`. Without a system Chrome set `OLYMPIC_BROWSER_PATH` (e.g. Playwright's Chromium, then also `OLYMPIC_BROWSER_SANDBOX=false`).
- Sync tuning: `OLYMPIC_SYNC_MAX_CHALLENGES` (challenge pages per run, freshest first, default 100; the history is loaded over several runs) and `OLYMPIC_REQUEST_DELAY` (seconds between requests, default 60: BoincStats shows a captcha when requests come too often). For a quick manual check use e.g. `OLYMPIC_SYNC_CRON="*/2 * * * *" OLYMPIC_SYNC_MAX_CHALLENGES=3`.
- Tests: `uv run --locked pytest` (single test: `uv run --locked pytest tests/test_models.py::test_tie_on_same_place_is_allowed`; tests against the real site: `uv run --locked pytest -m live`). With `OLYMPIC_TEST_DATABASE_URL` set (env or `.env`) each test run creates its own database `<name>_<random suffix>` on that server and drops it at the end (parallel runs are safe); otherwise they start a `postgres:18` testcontainer.

## Elastic APM

APM is opt-in (`OLYMPIC_APM_ENABLED=false` by default). `apm.py` owns a client per
application lifespan and uses public Client transaction APIs through pure ASGI
middleware (the agent's Starlette integration does not support our Starlette 1.x).
Do not add global instrumentation or downgrade FastAPI/Starlette. HTTP names use
route templates; health/static paths are excluded. Scheduler `sync` transactions
carry result/counters. Engine-local SQLAlchemy listeners add query spans with a
fixed operation name, duration, outcome and sanitized SQL in `db.statement`.
Preserve identifiers/placeholders, redact string/numeric literals and comments;
never include parameter values or connection URLs. Keep body/headers/locals disabled and serialized payload
redaction tests passing; never send Settings, DSNs, or sync error text.

`docker compose --profile observability up -d --build` adds Elasticsearch/Kibana/
APM Server 9.5.6, with bundled APM integration 9.5.6 installed idempotently by
`apm-setup` after `elastic-setup` prepares service credentials. Profile credentials
(`ELASTIC_PASSWORD`, `KIBANA_SYSTEM_PASSWORD`, `APM_WRITER_PASSWORD`,
`KIBANA_ENCRYPTION_KEY` >=32 characters) belong only in ignored `.docker-env`.
Kibana login is `elastic`; keep the encryption key across restarts. App still
only depends on db. For host-only APM start `elasticsearch kibana apm-setup
apm-server` with the same profile and `--build`, then use local `.env` with
`OLYMPIC_APM_SERVER_URL=http://127.0.0.1:8200`, environment `local`; container URL
is `http://apm-server:8200`, environment `docker`. An optional
`OLYMPIC_APM_SECRET_TOKEN` must match receiver and agents. Do not set conflicting
`ELASTIC_APM_*`. Ports 8200/5601 are loopback-only; Elasticsearch is internal.

See README for host resources, start/stop, Kibana environment selection, and
safe deletion of only `esdata`. `down` preserves it; `down -v` also deletes pgdata.
Quality gate must not need Elastic; use recording transport/local intake tests.
Real stack smoke tests must use an isolated Compose project and test credentials,
never alter existing dev volumes or contact real BoincStats during acceptance.

## Quality gate for Codex

Before completing changes to Python code, dependencies, or tool configuration (including the quality gate script), run:

```bash
./quality-gate.sh
```

The script first prepares dev + security + load dependencies with `uv sync --locked --extra load --group security`, then runs Ruff, mypy, pytest, Bandit and pip-audit with `uv run --locked --no-sync`, and separately installed Semgrep directly from PATH. It always runs all six checks after successful preparation, and exits with code 0 only when all pass. It resolves the repository root automatically and inherits `UV_PROJECT_ENVIRONMENT`; a preparation failure exits immediately with code 1. Ruff checks lint and import ordering; mypy checks application code, tests, migrations, scripts, and load tests using `pyproject.toml`. Pytest runs the default suite (live tests are excluded); database tests require `OLYMPIC_TEST_DATABASE_URL` or Docker for testcontainers, as described above. Bandit scans src/migrations/scripts/docker/load_tests; pip-audit checks an ephemeral locked requirements export including dev/security/load, without the local project and without resolving/installing dependencies. Semgrep scans those directories plus tests, Dockerfile and quality-gate.sh with p/security-audit and --error --strict. Missing tools, findings, scanner failures and dependency-export failures fail the gate; no silent skips. The audit database and Semgrep registry require network access. Keep check commands in the script.

Pytest measures line coverage of the entire `olympic_boinc` package with pytest-cov, prints uncovered lines, and fails when total coverage is below 90%. Do not lower the threshold or exclude application code just to pass.

The pip-audit export retains hashes and uses --require-hashes. Semgrep uses --no-git-ignore so uncommitted code is scanned; .semgrepignore overrides its default test exclusions and skips generated artifacts only.

The Ruff stage runs both `ruff check .` (including E501 at 100 characters) and
`ruff format --check .`. Apply formatting with `uv run --locked --no-sync ruff format .`.
Review logical spacing manually: the formatter cannot identify business-logic stages.

Fix diagnostics introduced by the change and rerun the checks after the final edit. Do not weaken rules, exclude project files, or add blanket `noqa` / `type: ignore` comments just to pass. If existing unrelated errors or an environment problem prevent a passing gate, report the failing command and remaining diagnostics explicitly; do not claim the gate passed. Documentation-only changes do not require these checks.

When behavior changes, add or update relevant tests. In the final response, state the outcome of the quality gate and tests.

## Python Code Style Guidelines

When writing or modifying Python code, prioritize human readability over compactness.

### Vertical Spacing

- Separate logically distinct blocks of code with a single blank line.
- Use blank lines between input validation, data preparation, business logic, external calls, and result handling.
- Do not compress an entire function into one visually dense block.
- Avoid unnecessary blank lines between closely related statements.
- Follow PEP 8 for spacing between top-level functions, classes, and methods.

### Code Structure

- Prefer short functions with a single clear responsibility.
- Use descriptive variable and function names.
- Extract complex conditions into well-named variables.
- Avoid deeply nested conditionals.
- Prefer explicit, readable code over clever one-liners.
- Separate error handling from the main business logic when practical.

### Comments

- Add comments to explain non-obvious decisions and constraints.
- Do not add comments that merely repeat what the code does.
- Prefer clear function names over explanatory comments.

### Formatting

- Use Ruff for standard formatting and linting.
- Keep line length at 100 characters.
- Preserve intentional blank lines that separate logical sections where compatible with Ruff.
- Do not sacrifice readability merely to reduce line count.

### Before Completing Changes

- Review modified functions for visual readability.
- Ensure distinct logical stages are easy to identify.
- Run Ruff and relevant tests.
- Follow the full quality gate requirements above for Python code, dependency, and tool configuration changes.

## Architecture

- `src/olympic_boinc/config.py` — `Settings` (pydantic-settings, `OLYMPIC_` prefix; `database_url` is required, no default), `get_settings()`.
- `src/olympic_boinc/db.py` — async engine / session factory, FastAPI `get_session` dependency (reads `app.state.session_factory`).
- `src/olympic_boinc/models.py` — `Challenge` (`challenge_type` project|team, unique `url`; only challenges with podium results are stored), `Team` (unique `display_name`: teams are identified by the exact name shown on BoincStats, no normalization), `ChallengeResult` (place 1..3, ties allowed, one result per team per challenge). Sync runs are not stored: APScheduler runs them, results go to the log.
- Data flow: `scraper` (fetch + parse BoincStats pages) → `sync` (store new podiums) → `db` ← `queries` → `api`; `scheduler` triggers `sync`; `csv_transfer` exports/imports podiums.
- `src/olympic_boinc/scraper/` — `fetcher.py`: `PageFetcher` protocol, `NodriverFetcher` (Chrome via nodriver, passes Cloudflare, throttling and retries via tenacity, `BlockedError` on Cloudflare/captcha pages); `parser.py`: pure `parse_overview` (completed challenges, canonical URL `/stats/{pchallenge|challenge}/team/list/{id}/rank`) and `parse_challenge` (podium; place from the Rank column or by credit), `ParseError` on unexpected markup; `types.py`: `ChallengeSummary`, `TeamPlacement`.
- `src/olympic_boinc/sync.py` — `run_sync(session_factory, fetcher, settings) -> SyncResult`: both overviews → challenges whose `url` is not stored, freshest first, up to `sync_max_challenges` → each saved in its own transaction (`ON CONFLICT DO NOTHING`). Stored challenges are never refetched; ones without results are retried next run. Status `failed` (an overview failed), `partial` (errors on single challenges, or a block stopped the run), `ok`; the summary goes to the log. `save_challenge(session, summary, placements)` (insert with podium, `False` if the url is already stored) is shared with the CSV import.
- `src/olympic_boinc/csv_transfer.py` — flat CSV, one row per podium place, no db ids (`COLUMNS`): `export_csv` (stable order `end_at, url, place, team` in "C" collation), `parse_csv` (checks the whole file, `CsvImportError` with all "line N: reason" errors; naive dates are UTC), `import_csv` (adds only unstored urls via `save_challenge`, one transaction, returns `(added, skipped)`), CLI `run(argv)`.
- `src/olympic_boinc/scheduler.py` — `build_scheduler` (APScheduler 3 `AsyncIOScheduler`, cron in UTC, `max_instances=1`, `coalesce=True`, job name `sync`; with `sync_on_startup` the job gets `next_run_time=now`), `sync_job` (a fresh fetcher per run, closed in `finally`; exceptions are logged) and `open_sync_log`/`close_sync_log`: a rotating file (`OLYMPIC_SYNC_LOG_FILE`, default `logs/sync.log` relative to the working directory) on the `apscheduler`, `olympic_boinc.scheduler`, `olympic_boinc.sync`, `olympic_boinc.scraper` loggers, opened by the lifespan only when the scheduler is enabled. The fetcher logs `GET <url>` before every attempt.
- `src/olympic_boinc/web/` — packaged HTML/CSS/vanilla JavaScript at `/` and `/static/`, no frontend build or CDN. Resources are resolved relative to the installed package; verify wheel/Docker delivery when changing them. Browser QA is separate from Python coverage.
- `src/olympic_boinc/queries.py` — read queries: `get_challenge_years` (distinct UTC end years across both types), `get_medal_table` (one aggregate query, Olympic order, filters by type and end date), `list_challenges`, `get_challenge`, `get_team_card`.
- `src/olympic_boinc/api/` — `app.py`: `create_app(settings)` with lifespan (engine/session factory in `app.state`, scheduler start/stop); `routers/`: `GET /api/medals`, `/api/challenges`, `/api/challenges/years` (before the ID route), `/api/challenges/{id}`, `/api/teams/{id}`, `/health`; `schemas.py`: response models. Read-only: there are no sync endpoints.
- `migrations/` — Alembic (async template); `env.py` also accepts an open connection via `config.attributes["connection"]` (used by tests).
- `tests/conftest.py` — session-scoped `engine` fixture (fresh DB + migrations), `database_url` fixture (unique DB per session, dropped afterwards), per-test `session` and `session_factory` fixtures wrapped in a rolled-back transaction; `tests/factories.py` — seeded challenges for query/API tests; HTML fixtures of real BoincStats pages in `tests/fixtures/`.

## Workflow: OpenSpec (spec-driven)

Development is driven by [OpenSpec](https://github.com/Fission-AI/OpenSpec) (`openspec` CLI, schema `spec-driven`, configured in `openspec/config.yaml`).

- `openspec/specs/` — the current source-of-truth capability specs.
- `openspec/changes/<name>/` — in-progress change proposals (proposal, design, delta specs, tasks).
- `openspec/changes/archive/` — completed changes.

Typical flow, via project skills in `.agents/skills/` (invoke them as `$skill-name` in Codex):
1. `$openspec-propose` (or `$openspec-explore` first to think through an idea) — create a change with all artifacts.
2. `$openspec-apply-change` — implement the change's tasks.
3. `$openspec-sync-specs` — merge delta specs into `openspec/specs/` without archiving (optional).
4. `$openspec-archive-change` — finalize the change and update main specs.

Use `$openspec-update-change` to revise an existing change’s planning artifacts.


Useful CLI commands: `openspec list` (changes; `--specs` for specs), `openspec show <item>`, `openspec status`, `openspec validate <item>`.

Project-wide context and per-artifact rules for OpenSpec belong in the `context:` / `rules:` sections of `openspec/config.yaml`.


## Tech Stack
- Python 3.13 (uv; `.python-version`, `uv.lock`, and `UV_PROJECT_ENVIRONMENT` as described above)
- FastApi
- PostgreSQL 18
- SQLAlchemy
- REST
- pytest
