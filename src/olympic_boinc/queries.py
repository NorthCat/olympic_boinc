"""Read queries behind the REST API: medal table, challenges with podiums, team card."""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Integer, Row, cast, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from olympic_boinc.models import Challenge, ChallengeResult, ChallengeType, Team

PLACE_MEDALS = {1: "gold", 2: "silver", 3: "bronze"}


@dataclass(frozen=True)
class Medals:
    gold: int
    silver: int
    bronze: int

    @property
    def total(self) -> int:
        return self.gold + self.silver + self.bronze


@dataclass(frozen=True)
class TeamCard:
    team: Team
    medals: Medals
    results: list[ChallengeResult]  # with `challenge` loaded, latest challenge first


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


async def get_medal_table(
    session: AsyncSession,
    challenge_type: ChallengeType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[Row]:
    """Teams with at least one medal, Olympic order: gold, silver, bronze (desc), then name.

    `date_from`/`date_to` filter by the challenge end and are inclusive (UTC days).
    Rows: `team_id`, `team_name`, `gold`, `silver`, `bronze`, `total`.
    """
    gold = func.count().filter(ChallengeResult.place == 1)
    silver = func.count().filter(ChallengeResult.place == 2)
    bronze = func.count().filter(ChallengeResult.place == 3)

    query = (
        select(
            Team.id.label("team_id"),
            Team.display_name.label("team_name"),
            gold.label("gold"),
            silver.label("silver"),
            bronze.label("bronze"),
            func.count().label("total"),
        )
        .select_from(ChallengeResult)
        .join(Team, Team.id == ChallengeResult.team_id)
        .join(Challenge, Challenge.id == ChallengeResult.challenge_id)
        .group_by(Team.id)
        .order_by(gold.desc(), silver.desc(), bronze.desc(), Team.display_name)
    )
    if challenge_type is not None:
        query = query.where(Challenge.challenge_type == challenge_type)
    if date_from is not None:
        query = query.where(Challenge.end_at >= _day_start(date_from))
    if date_to is not None:
        query = query.where(Challenge.end_at < _day_start(date_to + timedelta(days=1)))

    return list((await session.execute(query)).all())


def _with_podium():
    return selectinload(Challenge.results).selectinload(ChallengeResult.team)


async def get_challenge_years(session: AsyncSession) -> list[int]:
    """Distinct challenge end years in UTC, newest first, across both types."""
    year = cast(extract("year", func.timezone("UTC", Challenge.end_at)), Integer)

    return list(await session.scalars(select(year).distinct().order_by(year.desc())))


async def list_challenges(
    session: AsyncSession, challenge_type: ChallengeType | None, page: int, size: int
) -> tuple[list[Challenge], int]:
    """A page of challenges with podiums, latest end first, and the total number of challenges."""
    query = select(Challenge)
    if challenge_type is not None:
        query = query.where(Challenge.challenge_type == challenge_type)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar_one()

    challenges = await session.scalars(
        query.options(_with_podium())
        .order_by(Challenge.end_at.desc(), Challenge.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )

    return list(challenges), total


async def get_challenge(session: AsyncSession, challenge_id: int) -> Challenge | None:
    return await session.scalar(
        select(Challenge).where(Challenge.id == challenge_id).options(_with_podium())
    )


async def get_team_card(session: AsyncSession, team_id: int) -> TeamCard | None:
    team = await session.scalar(
        select(Team)
        .where(Team.id == team_id)
        .options(selectinload(Team.results).selectinload(ChallengeResult.challenge))
    )
    if team is None:
        return None

    places = Counter(result.place for result in team.results)
    results = sorted(
        team.results,
        key=lambda result: (result.challenge.end_at, result.challenge.id),
        reverse=True,
    )

    return TeamCard(team, Medals(places[1], places[2], places[3]), results)
