from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from olympic_boinc.api.app import create_app
from olympic_boinc.config import Settings
from olympic_boinc.db import get_session
from olympic_boinc.models import ChallengeType
from tests.factories import add_challenge, seed, team


def make_app(session_override):
    app = create_app(
        Settings(
            _env_file=None, database_url="postgresql+asyncpg://u:p@db/x", scheduler_enabled=False
        )
    )
    app.dependency_overrides[get_session] = session_override

    return app


@pytest.fixture
async def client(session) -> AsyncIterator[AsyncClient]:
    """Use the rolled-back test session for API requests without starting the lifespan."""

    async def override() -> AsyncIterator[AsyncSession]:
        yield session

    app = make_app(override)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def names(rows: list[dict]) -> list[str]:
    return [r["team_name"] for r in rows]


async def test_medal_table(client, session):
    await seed(session)

    response = await client.get("/api/medals")

    assert response.status_code == 200

    rows = response.json()

    assert names(rows) == ["Alpha", "Bravo", "Echo", "Charlie", "Aardvark", "Delta"]

    alpha = (await team(session, "Alpha")).id

    assert rows[0] == {
        "team_id": alpha,
        "team_name": "Alpha",
        "gold": 2,
        "silver": 0,
        "bronze": 1,
        "total": 3,
    }

    delta, bravo = rows[5], rows[1]

    assert (delta["silver"], bravo["silver"]) == (1, 2)  # shared 2nd place in c2: a silver for each


async def test_medal_table_filters(client, session):
    await seed(session)

    project = (await client.get("/api/medals", params={"challenge_type": "project"})).json()

    assert names(project) == ["Alpha", "Bravo", "Delta", "Charlie"]

    year = (
        await client.get("/api/medals", params={"from": "2025-01-01", "to": "2025-12-31"})
    ).json()

    assert names(year) == ["Alpha", "Bravo", "Charlie", "Delta"]

    everything = (await client.get("/api/medals", params={"challenge_type": "all"})).json()

    assert len(everything) == 6


@pytest.mark.parametrize(
    "params", [{"challenge_type": "foo"}, {"from": "yesterday"}, {"to": "2025-13-01"}]
)
async def test_medal_table_invalid_params(client, params):
    response = await client.get("/api/medals", params=params)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] in params


async def test_challenges_list(client, session):
    seeded = await seed(session)

    body = (await client.get("/api/challenges")).json()

    assert (body["total"], body["page"], body["size"]) == (4, 1, 50)
    assert [c["name"] for c in body["items"]] == ["c4", "c2", "c3", "c1"]

    c2 = body["items"][1]

    assert c2["id"] == seeded["c2"].id
    assert (c2["challenge_type"], c2["project_name"], c2["url"]) == (
        "project",
        "PrimeGrid",
        seeded["c2"].url,
    )
    assert datetime.fromisoformat(c2["end_at"]) == datetime(2025, 12, 31, 23, tzinfo=UTC)
    assert [(p["team_name"], p["place"], p["score"]) for p in c2["placements"]] == [
        ("Alpha", 1, 1000),
        ("Bravo", 2, 999),
        ("Delta", 2, 998),
    ]


async def test_challenge_years_empty(client):
    response = await client.get("/api/challenges/years")

    assert response.status_code == 200
    assert response.json() == []


async def test_challenge_years_all_pages_and_new_data(client, session):
    seeded = await seed(session)

    for i in range(51):
        await add_challenge(
            session, f"old{i}", ChallengeType.TEAM, datetime(2023, 1, 1, tzinfo=UTC), [("Alpha", 1)]
        )

    response = await client.get("/api/challenges/years")

    assert response.status_code == 200
    assert response.json() == [2026, 2025, 2023]
    assert (await client.get(f"/api/challenges/{seeded['c1'].id}")).status_code == 200

    await add_challenge(
        session, "new", ChallengeType.PROJECT, datetime(2027, 1, 1, tzinfo=UTC), [("Alpha", 1)]
    )

    assert (await client.get("/api/challenges/years")).json() == [2027, 2026, 2025, 2023]


async def test_challenges_pagination_and_filter(client, session):
    for i in range(25):
        await add_challenge(
            session,
            f"x{i:02}",
            ChallengeType.TEAM,
            datetime(2020, 1, 1 + i, tzinfo=UTC),
            [("Alpha", 1)],
        )

    await seed(session)

    page2 = (await client.get("/api/challenges", params={"page": 2, "size": 10})).json()
    everything = (await client.get("/api/challenges", params={"size": 200})).json()

    assert (page2["total"], page2["page"], page2["size"]) == (29, 2, 10)
    assert [c["id"] for c in page2["items"]] == [c["id"] for c in everything["items"][10:20]]

    project = (await client.get("/api/challenges", params={"challenge_type": "project"})).json()

    assert project["total"] == 2


@pytest.mark.parametrize(
    "params", [{"page": 0}, {"size": 0}, {"size": 201}, {"challenge_type": "foo"}]
)
async def test_challenges_invalid_params(client, params):
    assert (await client.get("/api/challenges", params=params)).status_code == 422


async def test_challenge_by_id(client, session):
    seeded = await seed(session)

    body = (await client.get(f"/api/challenges/{seeded['c3'].id}")).json()

    assert body["name"] == "c3"
    assert [(p["team_name"], p["place"]) for p in body["placements"]] == [
        ("Bravo", 1),
        ("Charlie", 2),
        ("Alpha", 3),
    ]
    assert (await client.get("/api/challenges/999999")).status_code == 404


async def test_team_card(client, session):
    seeded = await seed(session)
    alpha = (await team(session, "Alpha")).id

    body = (await client.get(f"/api/teams/{alpha}")).json()

    assert (body["id"], body["name"]) == (alpha, "Alpha")
    assert (body["gold"], body["silver"], body["bronze"], body["total"]) == (2, 0, 1, 3)
    assert [(c["id"], c["place"]) for c in body["challenges"]] == [
        (seeded["c2"].id, 1),
        (seeded["c3"].id, 3),
        (seeded["c1"].id, 1),
    ]
    assert [c for c in body["challenges"] if c["place"] == 1] == [
        body["challenges"][0],
        body["challenges"][2],
    ]
    assert (await client.get("/api/teams/999999")).status_code == 404


async def test_health_ok(client):
    response = await client.get("/health")

    assert (response.status_code, response.json()) == (200, {"status": "ok"})


async def test_health_database_unavailable():
    engine = create_async_engine(
        "postgresql+asyncpg://u:p@127.0.0.1:1/x"
    )  # nothing listens on port 1

    async def override() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine) as s:
            yield s

    try:
        async with AsyncClient(
            transport=ASGITransport(app=make_app(override)), base_url="http://test"
        ) as c:
            response = await c.get("/health")
    finally:
        await engine.dispose()

    assert (response.status_code, response.json()) == (503, {"status": "unavailable"})


def test_all_endpoints_in_openapi():
    schema = make_app(get_session).openapi()

    assert set(schema["paths"]) == {
        "/api/medals",
        "/api/challenges",
        "/api/challenges/years",
        "/api/challenges/{challenge_id}",
        "/api/teams/{team_id}",
        "/health",
    }
    assert {"MedalRow", "ChallengeOut", "PlacementOut", "TeamOut", "Page_ChallengeOut_"} <= set(
        schema["components"]["schemas"]
    )

    medal_params = {p["name"] for p in schema["paths"]["/api/medals"]["get"]["parameters"]}

    assert medal_params == {"challenge_type", "from", "to"}
