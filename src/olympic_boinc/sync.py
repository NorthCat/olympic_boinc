"""Sync of completed BoincStats challenges and their podium teams into the database."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from olympic_boinc.config import Settings
from olympic_boinc.models import Challenge, ChallengeResult, ChallengeType, Team
from olympic_boinc.scraper.fetcher import BlockedError, FetchError, PageFetcher
from olympic_boinc.scraper.parser import parse_challenge, parse_overview
from olympic_boinc.scraper.types import ChallengeSummary, TeamPlacement

logger = logging.getLogger(__name__)

BASE_URL = "https://www.boincstats.com"
OVERVIEW_URLS = {
    ChallengeType.PROJECT: f"{BASE_URL}/stats/pchallenge/team/overview",
    ChallengeType.TEAM: f"{BASE_URL}/stats/challenge/team/overview",
}


class SyncStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"  # errors on single challenges or the run was stopped by a block
    FAILED = "failed"  # an overview page could not be fetched or parsed


@dataclass
class SyncResult:
    status: SyncStatus = SyncStatus.OK
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    added: int = 0
    skipped: int = 0  # no results on the page or an error
    deferred: int = 0  # not loaded in this run: over the limit or after a block
    errors: list[str] = field(default_factory=list)


def _error(result: SyncResult, url: str, exc: Exception) -> None:
    # FetchError already includes the URL, so reuse only its detail.
    detail = exc.detail if isinstance(exc, FetchError) else exc
    message = f"{url}: {type(exc).__name__}: {detail}"
    result.errors.append(message)
    logger.error(message, exc_info=exc)


async def _select_candidates(
    session_factory: async_sessionmaker[AsyncSession], challenges: list[ChallengeSummary]
) -> list[ChallengeSummary]:
    """Challenges not stored yet, freshest first."""
    async with session_factory() as session:
        stored = set(await session.scalars(select(Challenge.url)))

    new = {c.url: c for c in challenges if c.url not in stored}

    return sorted(new.values(), key=lambda c: c.end_at, reverse=True)


def _best_places(
    summary: ChallengeSummary, placements: list[TeamPlacement]
) -> dict[str, TeamPlacement]:
    best: dict[str, TeamPlacement] = {}

    for placement in placements:
        if placement.team_name in best:
            logger.warning(
                "%s: team %r is listed more than once, keeping the best place",
                summary.url,
                placement.team_name,
            )
            if best[placement.team_name].place <= placement.place:
                continue

        best[placement.team_name] = placement

    return best


async def save_challenge(
    session: AsyncSession, summary: ChallengeSummary, placements: list[TeamPlacement]
) -> bool:
    """Store a challenge with its podium; return False if another run already stored it."""
    challenge_id = await session.scalar(
        insert(Challenge)
        .values(
            challenge_type=summary.challenge_type,
            name=summary.name,
            project_name=summary.project_name,
            start_at=summary.start_at,
            end_at=summary.end_at,
            url=summary.url,
        )
        .on_conflict_do_nothing(index_elements=[Challenge.url])
        .returning(Challenge.id)
    )
    if challenge_id is None:
        return False

    best = _best_places(summary, placements)
    team_names = list(best)

    await session.execute(
        insert(Team)
        .values([{"display_name": team_name} for team_name in team_names])
        .on_conflict_do_nothing(index_elements=[Team.display_name])
    )
    team_rows = await session.execute(
        select(Team.display_name, Team.id).where(Team.display_name.in_(team_names))
    )
    team_ids = dict(team_rows.all())
    podium_rows = [
        {
            "challenge_id": challenge_id,
            "team_id": team_ids[team_name],
            "place": placement.place,
            "score": placement.score,
        }
        for team_name, placement in best.items()
    ]

    await session.execute(insert(ChallengeResult).values(podium_rows))

    return True


def _log_result(result: SyncResult) -> None:
    if result.finished_at is None:
        raise ValueError("Cannot log an unfinished sync result")

    level = {
        SyncStatus.OK: logging.INFO,
        SyncStatus.PARTIAL: logging.WARNING,
        SyncStatus.FAILED: logging.ERROR,
    }
    duration = (result.finished_at - result.started_at).total_seconds()
    logger.log(
        level[result.status],
        "sync %s in %.0f s: added=%d skipped=%d deferred=%d errors=%d",
        result.status,
        duration,
        result.added,
        result.skipped,
        result.deferred,
        len(result.errors),
    )


async def run_sync(
    session_factory: async_sessionmaker[AsyncSession], fetcher: PageFetcher, settings: Settings
) -> SyncResult:
    """Sync new completed challenges from both overviews, up to `sync_max_challenges` pages."""
    result = SyncResult()

    try:
        challenges: list[ChallengeSummary] = []

        for challenge_type, url in OVERVIEW_URLS.items():
            try:
                challenges += parse_overview(await fetcher.get(url), challenge_type, BASE_URL)
            except Exception as exc:
                result.status = SyncStatus.FAILED
                _error(result, url, exc)

                return result

        candidates = await _select_candidates(session_factory, challenges)
        to_load = candidates[: settings.sync_max_challenges]
        result.deferred = len(candidates) - len(to_load)

        for index, summary in enumerate(to_load):
            try:
                placements = parse_challenge(await fetcher.get(summary.url))
                if placements:
                    async with session_factory() as session, session.begin():
                        saved = await save_challenge(session, summary, placements)
                else:
                    saved = False
            except BlockedError as exc:
                result.status = SyncStatus.PARTIAL
                result.deferred += len(to_load) - index
                _error(result, summary.url, exc)
                break
            except Exception as exc:
                result.status = SyncStatus.PARTIAL
                result.skipped += 1
                _error(result, summary.url, exc)
                continue

            if saved:
                result.added += 1
            else:
                result.skipped += 1

        return result
    finally:
        result.finished_at = datetime.now(UTC)
        _log_result(result)
