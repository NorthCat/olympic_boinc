import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL_VAR = "MYAPP_TEST_DATABASE_URL"  # TODO: use the project's env prefix
POSTGRES_IMAGE = "postgres:18"  # TODO: match the production PostgreSQL version


def alembic_config(connection=None) -> Config:
    """Alembic config; with `connection`, migrations run over that already open (sync-facing) connection."""
    cfg = Config(str(ROOT / "alembic.ini"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


async def run_alembic(conn: AsyncConnection, fn, *args) -> None:
    await conn.run_sync(lambda sync_conn: fn(alembic_config(sync_conn), *args))


async def admin_execute(url: str, statement: str) -> None:
    """Run a statement against the server's `postgres` maintenance database, outside a transaction."""
    admin = create_async_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(statement))
    finally:
        await admin.dispose()


@pytest.fixture(scope="session")
def server_url() -> Iterator[str]:
    """Existing server from the test URL variable (env or .env), otherwise a PostgreSQL testcontainer."""
    url = os.environ.get(TEST_DATABASE_URL_VAR) or dotenv_values(ROOT / ".env").get(TEST_DATABASE_URL_VAR)
    if url:
        yield url
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
async def database_url(server_url: str) -> AsyncIterator[str]:
    """A uniquely named database for this test session, dropped afterwards.

    The name is `<database from server_url>_<random suffix>`, so parallel test runs don't collide.
    """
    base = make_url(server_url)
    name = f"{base.database}_{uuid.uuid4().hex[:8]}"
    await admin_execute(server_url, f'CREATE DATABASE "{name}"')
    try:
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        await admin_execute(server_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await run_alembic(conn, command.upgrade, "head")
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session inside an outer transaction that is rolled back after the test."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False) as s:
            yield s
        await trans.rollback()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Session factory whose sessions (and their commits) run inside an outer transaction rolled back after the test."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        yield async_sessionmaker(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        await trans.rollback()
