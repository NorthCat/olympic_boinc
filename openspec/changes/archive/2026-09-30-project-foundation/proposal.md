# Proposal

## Why

The repository is empty. Before collecting data from BoincStats and counting medals, we need an application skeleton, configuration, a PostgreSQL connection, and a data model. All subsequent changes depend on them: `boincstats-fetching`, `challenge-parsing`, `challenge-sync`, `scheduled-sync`, `medals-rest-api`.

## What Changes

- Python package `olympic_boinc` (src-layout) with `pyproject.toml` and dependencies.
- `docker-compose.yml` with PostgreSQL 18 for local development.
- Configuration through environment variables.
- Asynchronous database connection (SQLAlchemy 2 + asyncpg) and Alembic migrations.
- Data model: challenges, teams, results (podium placements).
- Team identity: the same team is identified by an exact BoincStats name match.
- Pytest infrastructure with a real PostgreSQL database.

## Capabilities

### New Capabilities
- `data-model`: storage of challenges, teams, and podium placements, and rules for team and challenge identity.

### Modified Capabilities

## Impact

- New files: `pyproject.toml`, `docker-compose.yml`, `alembic.ini`, `migrations/`, `src/olympic_boinc/{config,db,models}.py`, `tests/`.
- Dependencies: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, pydantic-settings; for development: pytest, pytest-asyncio, httpx, testcontainers[postgres].
- `../../../../AGENTS.md`: commands for running, tests, and migrations.
