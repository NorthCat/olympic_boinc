"""Test data: challenges with podiums written straight to the database."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from olympic_boinc.models import Challenge, ChallengeResult, ChallengeType, Team


async def team(session: AsyncSession, name: str) -> Team:
    found = await session.scalar(select(Team).where(Team.display_name == name))
    if found is None:
        found = Team(display_name=name)
        session.add(found)
        await session.flush()

    return found


async def add_challenge(
    session: AsyncSession,
    name: str,
    challenge_type: ChallengeType,
    end_at: datetime,
    podium: list[tuple[str, int]],
) -> Challenge:
    challenge = Challenge(
        challenge_type=challenge_type,
        name=name,
        project_name="PrimeGrid" if challenge_type == ChallengeType.PROJECT else None,
        start_at=end_at.replace(year=end_at.year - 1),
        end_at=end_at,
        url=f"https://www.boincstats.com/test/{name}",
    )
    session.add(challenge)
    await session.flush()

    for i, (team_name, place) in enumerate(podium):
        t = await team(session, team_name)
        session.add(
            ChallengeResult(challenge_id=challenge.id, team_id=t.id, place=place, score=1000 - i)
        )

    await session.flush()

    return challenge


async def seed(session: AsyncSession) -> dict[str, Challenge]:
    """Seed four challenges: c2 has a tied silver and ends in late 2025; c4 ends in 2026."""
    p, t = ChallengeType.PROJECT, ChallengeType.TEAM
    challenges = {
        "c1": await add_challenge(
            session,
            "c1",
            p,
            datetime(2025, 3, 1, 12, tzinfo=UTC),
            [("Alpha", 1), ("Bravo", 2), ("Charlie", 3)],
        ),
        "c2": await add_challenge(
            session,
            "c2",
            p,
            datetime(2025, 12, 31, 23, tzinfo=UTC),
            [("Alpha", 1), ("Bravo", 2), ("Delta", 2)],
        ),
        "c3": await add_challenge(
            session,
            "c3",
            t,
            datetime(2025, 6, 1, tzinfo=UTC),
            [("Bravo", 1), ("Charlie", 2), ("Alpha", 3)],
        ),
        "c4": await add_challenge(
            session, "c4", t, datetime(2026, 1, 1, tzinfo=UTC), [("Echo", 1), ("Aardvark", 2)]
        ),
    }
    await session.commit()

    return challenges
