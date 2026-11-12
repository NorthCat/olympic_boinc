 # Design

## Context

The repository is empty (see proposal.md). The stack is specified in `../../../../AGENTS.md`: Python 3.14, FastAPI, PostgreSQL 18, SQLAlchemy, pytest. Data requirements are in `specs/data-model/spec.md`.

## Goals / Non-Goals

**Goals:**
- A package structure that accommodates subsequent changes without restructuring.
- A reproducible local database and tests against real PostgreSQL.

**Non-Goals:**
- Page fetching and parsing, sync, API, and scheduler. These are separate changes.
- Deployment and CI.

## Decisions

- **src-layout** (`src/olympic_boinc/`). This prevents tests from accidentally importing the package from the repository root. Modules:
  - `config.py`;
  - `db.py`;
  - `models.py`;
  - `scraper/`, `sync.py`, `scheduler.py`, and `api/` will appear later.
- **SQLAlchemy 2 async + asyncpg.** FastAPI is asynchronous; sync and the scheduler will also run in the event loop. The alternative is synchronous psycopg in a threadpool. It was rejected because it would result in two styles of database access.
- **Alembic with the async template** (`alembic init -t async`). Migrations are generated from `models.py`.
- **Schema:**
  - `challenge`: `id` PK, `challenge_type` (enum `challenge_type`: project|team), `name`, `project_name` (null), `start_at` / `end_at` (timestamptz), `url` (UNIQUE).
  - `team`: `id` PK, `display_name` (UNIQUE).
  - `challenge_result`: `id` PK, `challenge_id` FK ON DELETE CASCADE, `team_id` FK, `place` smallint `CHECK (place BETWEEN 1 AND 3)`, `score` numeric null. `UNIQUE(challenge_id, team_id)`, index on `(team_id, place)` for medal standings.
- **Synchronization runs are not stored in the database.** APScheduler starts synchronization; run summaries and errors are written to the application log.
- **A challenge is identified by `url`** — the absolute link to its page on BoincStats. We do not store a separate BoincStats identifier: the link is already unique and distinguishes project and team challenges.
- **Only challenges with podium finishers are stored.** Challenges without results and those that could not be fetched or parsed are not saved, so status and fetch time fields are unnecessary.
- **Team name without normalization.** We assume BoincStats displays team names correctly and consistently, so a team is identified by its exact name (`display_name`, UNIQUE). No separate normalized key is stored. If spelling differences appear in real data, normalization will be added in a separate change.
- **Configuration through pydantic-settings** with the `OLYMPIC_` prefix and `.env`. Fields: `database_url`, `sync_cron` (default `"0 3 * * *"`), `fetcher` (`curl_cffi`|`playwright`), `request_delay` (seconds), `scheduler_enabled`.
- **Test database:** if `OLYMPIC_TEST_DATABASE_URL` is set, tests recreate this database on the existing server; otherwise they start testcontainers (`postgres:18`). Docker is unavailable in the development environment without the `docker` group, so the main option is local PostgreSQL 18 (role `olympic` with `CREATEDB`). A session-scoped fixture runs `alembic upgrade head`. Each test runs in a transaction that is rolled back. SQLite is unsuitable: PostgreSQL enum, `CHECK`, and `FILTER` are needed.

## Risks / Trade-offs

- [Python 3.14 is new, and some packages may lack wheels (asyncpg, curl_cffi)] → verify installation as the very first task; if no wheel exists, build from source or use psycopg 3 (async) instead of asyncpg.
- [testcontainers requires Docker] → local PostgreSQL through `OLYMPIC_TEST_DATABASE_URL` is used by default; a container is the fallback.
