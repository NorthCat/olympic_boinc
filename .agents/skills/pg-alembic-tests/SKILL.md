---
name: pg-alembic-tests
description: Set up or fix pytest infrastructure for a Python project with PostgreSQL + SQLAlchemy + Alembic - a uniquely named test database created per test run and always dropped afterwards, per-test transaction rollback, and migration tests including the stairway test (upgrade -> downgrade -> upgrade for every revision). Use when adding tests that touch a PostgreSQL database, writing conftest.py database fixtures, adding or reviewing Alembic migrations, or when a project lacks a stairway migration test.
---

# PostgreSQL + Alembic test infrastructure

Ready-made, verified templates live next to this file:

- `templates/conftest.py` - database fixtures.
- `templates/test_migrations.py` - migration tests.

Copy them into the project's `tests/` and adapt the `TODO` lines. Don't rewrite them from scratch.

## Requirements (non-negotiable)

1. **Unique test database per run.** The name is `<base name>_<random suffix>`, never a fixed name, so parallel runs (several terminals, CI jobs, agents) don't collide.
2. **Always dropped.** The database is dropped in the fixture's `finally` (so also when tests fail), with `DROP DATABASE ... WITH (FORCE)` to kick out leftover connections.
3. **Schema via migrations, not `metadata.create_all()`.** The session fixture runs `alembic upgrade head`, so tests exercise the real migrations.
4. **Per-test isolation by rollback.** Every test runs inside an outer transaction that is rolled back; app code that commits uses `join_transaction_mode="create_savepoint"`.
5. **Two migration tests:**
   - base <-> head round trip: `downgrade base`, check tables are gone, `upgrade head`, check they're back;
   - **stairway**: for every revision, oldest first: `upgrade rev` -> `downgrade -1` -> `upgrade rev`. It catches incomplete downgrades of individual migrations (leftover enum types, indexes, sequences) that the round trip can miss once there are several migrations.

## How the templates work

- `server_url`: takes an existing server from the `<PREFIX>_TEST_DATABASE_URL` variable (env or `.env`), otherwise starts a `postgres` testcontainer. The role needs `CREATEDB`.
- `database_url`: creates the unique database through the `postgres` maintenance DB (AUTOCOMMIT) and drops it at the end.
- `engine`: session-scoped, migrates to head once.
- Migration tests run inside a transaction and roll back: PostgreSQL DDL is transactional, so the shared database stays at head for other tests.

## Adapting

- **Alembic `env.py` must accept an open connection** - the tests migrate over their own connection and event loop:

  ```python
  def run_migrations_online() -> None:
      # Tests pass an already open connection to run inside their own event loop.
      connection = config.attributes.get("connection")
      if connection is not None:
          do_run_migrations(connection)
      else:
          asyncio.run(run_async_migrations())
  ```

  `env.py` must also not need the app's database settings when a connection is passed.
- **Downgrades must drop PostgreSQL enum types** (`sa.Enum(name=...).drop(op.get_bind(), checkfirst=True)`) - autogenerate doesn't do it, and the stairway test fails with `type "..." already exists` without it.
- Set `TEST_DATABASE_URL_VAR`, `POSTGRES_IMAGE` (match production) and `TABLES`.
- Dev dependencies: `pytest`, `pytest-asyncio`, `asyncpg`, `python-dotenv`, `testcontainers[postgres]`.
- pytest config (async templates assume a session-wide loop):

  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  asyncio_default_fixture_loop_scope = "session"
  asyncio_default_test_loop_scope = "session"
  ```

- `tests/` must be a package (`tests/__init__.py`) for `from tests.conftest import ...`.
- **Sync SQLAlchemy** (psycopg): same structure with `create_engine`, `Session`, plain fixtures; `command.upgrade(alembic_config(conn), ...)` directly instead of `run_alembic`.
- **Merge revisions** (tuple `down_revision`): `downgrade -1` is ambiguous there; step down to one explicit parent instead.
- **Migrations that can't run in a transaction** (`CREATE INDEX CONCURRENTLY`, `ALTER TYPE ... ADD VALUE` on old PostgreSQL): run the migration tests on a dedicated fresh database instead of the rollback trick.

## Verify

Run the suite, then make sure the stairway test really bites: temporarily remove a `drop` from some migration's `downgrade()` (e.g. the enum drop) - the stairway test must fail. Revert. Also check no `<name>_xxxxxxxx` databases are left on the server after the run (`psql -l`).
