import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from tests.conftest import alembic_config, run_alembic

TABLES = {"my_table"}  # TODO: the tables created by the migrations

# Oldest first.
REVISIONS = list(reversed(list(ScriptDirectory.from_config(alembic_config()).walk_revisions())))


async def table_names(conn) -> set[str]:
    return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))


async def test_migrations_downgrade_and_upgrade(engine):
    # PostgreSQL DDL is transactional, so the round trip is rolled back afterwards.
    async with engine.connect() as conn:
        trans = await conn.begin()

        await run_alembic(conn, command.downgrade, "base")
        assert not TABLES & await table_names(conn)

        await run_alembic(conn, command.upgrade, "head")
        assert TABLES <= await table_names(conn)

        await trans.rollback()


@pytest.mark.parametrize("revision", REVISIONS, ids=lambda r: r.revision)
async def test_migrations_stairway(engine, revision):
    """Each migration on its own: upgrade -> downgrade -> upgrade again.

    The second upgrade fails if the downgrade left something behind (e.g. an enum type), and
    the downgrade fails if it doesn't match the upgrade.
    """
    async with engine.connect() as conn:
        trans = await conn.begin()

        await run_alembic(conn, command.downgrade, revision.down_revision or "base")
        await run_alembic(conn, command.upgrade, revision.revision)
        await run_alembic(conn, command.downgrade, "-1")
        await run_alembic(conn, command.upgrade, revision.revision)

        await trans.rollback()
