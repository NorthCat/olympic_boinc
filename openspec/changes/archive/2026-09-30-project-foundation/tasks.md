# Tasks

## 1. Project skeleton

- [x] 1.1 Create `pyproject.toml` (src-layout, package `olympic_boinc`, Python >=3.14). Dependencies: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings; dev: pytest, pytest-asyncio, httpx, testcontainers[postgres]. Verification: `pip install -e .[dev]` in a venv completes without errors.
- [x] 1.2 Create `docker-compose.yml` with a `db` service (postgres:18, volume, healthcheck, port 5433) as an alternative, and `.env.example`. The main database is local PostgreSQL 18 (role `olympic`). Verification: `psql` connects to the database from `.env`, and `docker compose config` is valid.
- [x] 1.3 Implement `config.py` (pydantic-settings, `OLYMPIC_` prefix, fields from design.md). Verification: unit test for defaults and environment overrides.
- [x] 1.4 Implement `db.py`: async engine, `async_sessionmaker`, `get_session` dependency for FastAPI. Verification: a test executes `SELECT 1`.

## 2. Data model

- [x] 2.1 A team is identified by its exact name (`team.display_name` UNIQUE), without normalization. Verification: tests reject a duplicate name and treat names differing in case as different teams.
- [x] 2.2 Define the `Challenge`, `Team`, and `ChallengeResult` models in `models.py` with constraints from design.md.
- [x] 2.3 Initialize Alembic (async template) and generate the first migration. Verification: `alembic upgrade head` on a clean database and `alembic downgrade base` pass.

## 3. Tests and documentation

- [x] 3.1 `tests/conftest.py`: database from `OLYMPIC_TEST_DATABASE_URL` (recreated) or a postgres:18 container, migrations on startup, a session with rollback for each test. Verification: `pytest` starts the database.
- [x] 3.2 Test scenarios from `specs/data-model/spec.md`: challenge `url` uniqueness, rejection of `place` outside 1..3, ties, prohibition of two results for one team in one challenge. Verification: `pytest` passes.
- [x] 3.3 Update `../../../../AGENTS.md`: installation, database startup, migrations, tests, package structure. Verification: commands from the file execute as described.
