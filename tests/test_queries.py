from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text

from olympic_boinc.models import ChallengeType
from olympic_boinc.queries import (
    get_challenge,
    get_challenge_years,
    get_medal_table,
    get_team_card,
    list_challenges,
)
from tests.factories import add_challenge, seed, team


async def test_challenge_years_empty(session):
    assert await get_challenge_years(session) == []


async def test_challenge_years_unique_sorted(session):
    await seed(session)
    await add_challenge(
        session, "older", ChallengeType.TEAM, datetime(2023, 1, 1, tzinfo=UTC), [("Alpha", 1)]
    )

    assert await get_challenge_years(session) == [2026, 2025, 2023]


@pytest.mark.parametrize(
    ("timezone", "end_at", "year"),
    [
        ("Pacific/Auckland", datetime(2025, 12, 31, 23, 30, tzinfo=UTC), 2025),
        ("America/Los_Angeles", datetime(2026, 1, 1, tzinfo=UTC), 2026),
    ],
)
async def test_challenge_years_are_utc(session, timezone, end_at, year):
    await add_challenge(session, "boundary", ChallengeType.PROJECT, end_at, [("Alpha", 1)])
    await session.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": timezone})

    assert await get_challenge_years(session) == [year]


def table(rows) -> list[tuple[str, int, int, int, int]]:
    return [(r.team_name, r.gold, r.silver, r.bronze, r.total) for r in rows]


async def test_medal_table_olympic_order_and_ties(session):
    await seed(session)

    assert table(await get_medal_table(session)) == [
        ("Alpha", 2, 0, 1, 3),  # 2 gold beats 1 gold + 2 silver
        ("Bravo", 1, 2, 0, 3),
        ("Echo", 1, 0, 0, 1),
        ("Charlie", 0, 1, 1, 2),
        ("Aardvark", 0, 1, 0, 1),  # equal medals: by name
        ("Delta", 0, 1, 0, 1),  # shared 2nd place in c2 is a silver for both
    ]


@pytest.mark.parametrize(
    ("challenge_type", "expected"),
    [
        (
            ChallengeType.PROJECT,
            [
                ("Alpha", 2, 0, 0, 2),
                ("Bravo", 0, 2, 0, 2),
                ("Delta", 0, 1, 0, 1),
                ("Charlie", 0, 0, 1, 1),
            ],
        ),
        (
            ChallengeType.TEAM,
            [
                ("Bravo", 1, 0, 0, 1),
                ("Echo", 1, 0, 0, 1),
                ("Aardvark", 0, 1, 0, 1),
                ("Charlie", 0, 1, 0, 1),
                ("Alpha", 0, 0, 1, 1),
            ],
        ),
    ],
)
async def test_medal_table_by_challenge_type(session, challenge_type, expected):
    await seed(session)

    assert table(await get_medal_table(session, challenge_type)) == expected


async def test_medal_table_period_includes_both_end_days(session):
    await seed(session)

    year_2025 = table(
        await get_medal_table(session, date_from=date(2025, 1, 1), date_to=date(2025, 12, 31))
    )

    assert year_2025 == [
        ("Alpha", 2, 0, 1, 3),
        ("Bravo", 1, 2, 0, 3),
        ("Charlie", 0, 1, 1, 2),
        ("Delta", 0, 1, 0, 1),
    ]

    one_day = table(
        await get_medal_table(session, date_from=date(2025, 3, 1), date_to=date(2025, 3, 1))
    )

    assert one_day == [("Alpha", 1, 0, 0, 1), ("Bravo", 0, 1, 0, 1), ("Charlie", 0, 0, 1, 1)]

    since_2026 = table(await get_medal_table(session, date_from=date(2026, 1, 1)))

    assert since_2026 == [("Echo", 1, 0, 0, 1), ("Aardvark", 0, 1, 0, 1)]


async def test_list_challenges_latest_first_with_podium(session):
    seeded = await seed(session)

    challenges, total = await list_challenges(session, None, page=1, size=50)

    assert total == 4
    assert [c.name for c in challenges] == ["c4", "c2", "c3", "c1"]

    c2 = challenges[1]

    assert [(r.team.display_name, r.place) for r in c2.results] == [
        ("Alpha", 1),
        ("Bravo", 2),
        ("Delta", 2),
    ]
    assert c2.id == seeded["c2"].id


async def test_list_challenges_filter_and_pages(session):
    await seed(session)

    for i in range(25):
        await add_challenge(
            session,
            f"x{i:02}",
            ChallengeType.TEAM,
            datetime(2020, 1, 1 + i, tzinfo=UTC),
            [("Alpha", 1)],
        )

    team_only, total = await list_challenges(session, ChallengeType.TEAM, page=1, size=50)

    assert total == 27 and {c.challenge_type for c in team_only} == {ChallengeType.TEAM}

    page2, total = await list_challenges(session, None, page=2, size=10)
    everything, _ = await list_challenges(session, None, page=1, size=200)

    assert total == 29
    assert [c.id for c in page2] == [c.id for c in everything[10:20]]


async def test_get_challenge(session):
    seeded = await seed(session)

    challenge = await get_challenge(session, seeded["c3"].id)

    assert challenge is not None
    assert challenge.name == "c3"
    assert [(r.team.display_name, r.place) for r in challenge.results] == [
        ("Bravo", 1),
        ("Charlie", 2),
        ("Alpha", 3),
    ]
    assert await get_challenge(session, -1) is None


async def test_team_card(session):
    await seed(session)
    alpha = (await team(session, "Alpha")).id

    card = await get_team_card(session, alpha)

    assert card is not None
    assert card.team.display_name == "Alpha"
    assert (card.medals.gold, card.medals.silver, card.medals.bronze, card.medals.total) == (
        2,
        0,
        1,
        3,
    )
    assert [(r.challenge.name, r.place) for r in card.results] == [("c2", 1), ("c3", 3), ("c1", 1)]
    assert await get_team_card(session, -1) is None
