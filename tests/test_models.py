from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from olympic_boinc.models import Challenge, ChallengeResult, ChallengeType, Team


def make_challenge(url_id="42", challenge_type=ChallengeType.PROJECT) -> Challenge:
    return Challenge(
        challenge_type=challenge_type,
        name="Pentathlon",
        project_name="Einstein@Home",
        start_at=datetime(2025, 5, 5, tzinfo=UTC),
        end_at=datetime(2025, 5, 19, tzinfo=UTC),
        url=f"https://boincstats.com/stats/pchallenge/team/chat/{url_id}",
    )


async def test_challenge_with_results(session):
    gold, silver = Team(display_name="SETI.Germany"), Team(display_name="TSBT")
    challenge = make_challenge()
    challenge.results = [
        ChallengeResult(team=gold, place=1, score=Decimal("123456.78")),
        ChallengeResult(team=silver, place=2),
    ]
    session.add(challenge)
    await session.flush()

    stored = await session.scalar(select(Challenge).where(Challenge.id == challenge.id))

    assert stored.challenge_type is ChallengeType.PROJECT
    assert [(r.team.display_name, r.place) for r in stored.results] == [
        ("SETI.Germany", 1),
        ("TSBT", 2),
    ]


async def test_same_url_is_rejected(session):
    session.add(make_challenge("7", ChallengeType.PROJECT))
    await session.flush()

    session.add(make_challenge("7", ChallengeType.TEAM))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_team_display_name_is_unique(session):
    session.add(Team(display_name="SETI.Germany"))
    await session.flush()

    session.add(Team(display_name="SETI.Germany"))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_team_names_are_compared_exactly(session):
    session.add_all([Team(display_name="SETI.Germany"), Team(display_name="seti.germany")])
    await session.flush()

    assert len((await session.scalars(select(Team))).all()) == 2


async def test_tie_on_same_place_is_allowed(session):
    challenge = make_challenge()
    challenge.results = [
        ChallengeResult(team=Team(display_name="A"), place=1),
        ChallengeResult(team=Team(display_name="B"), place=2),
        ChallengeResult(team=Team(display_name="C"), place=2),
    ]
    session.add(challenge)
    await session.flush()

    assert sorted(r.place for r in challenge.results) == [1, 2, 2]


@pytest.mark.parametrize("place", [0, 4])
async def test_place_outside_podium_is_rejected(session, place):
    challenge = make_challenge()
    challenge.results = [ChallengeResult(team=Team(display_name="A"), place=place)]
    session.add(challenge)

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_team_has_one_result_per_challenge(session):
    team = Team(display_name="A")
    challenge = make_challenge()
    challenge.results = [ChallengeResult(team=team, place=1), ChallengeResult(team=team, place=2)]
    session.add(challenge)

    with pytest.raises(IntegrityError):
        await session.flush()
