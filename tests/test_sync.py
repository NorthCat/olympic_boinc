import logging
from collections.abc import Mapping
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from olympic_boinc.config import Settings
from olympic_boinc.models import Challenge, ChallengeResult, ChallengeType, Team
from olympic_boinc.scraper.fetcher import BlockedError
from olympic_boinc.scraper.parser import parse_challenge, parse_overview
from olympic_boinc.sync import (
    BASE_URL,
    OVERVIEW_URLS,
    SyncResult,
    SyncStatus,
    _log_result,
    run_sync,
)

FIXTURES = Path(__file__).parent / "fixtures"
OVERVIEW_FIXTURES = {
    ChallengeType.PROJECT: "pchallenge_overview.html",
    ChallengeType.TEAM: "challenge_overview.html",
}


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


# Completed challenges of both fixture overviews in the order the sync loads them: latest end first.
FRESHEST = sorted(
    (
        c
        for t, name in OVERVIEW_FIXTURES.items()
        for c in parse_overview(fixture(name), t, BASE_URL)
    ),
    key=lambda c: c.end_at,
    reverse=True,
)
TOTAL = len(FRESHEST)


def test_logging_requires_finished_sync():
    with pytest.raises(ValueError, match="unfinished sync"):
        _log_result(SyncResult())


class FakeFetcher:
    """Serve fixture overviews and supplied pages; return no results for other challenges."""

    def __init__(self, pages: Mapping[str, str | Exception] | None = None) -> None:
        self.pages: dict[str, str | Exception] = {
            url: fixture(OVERVIEW_FIXTURES[t]) for t, url in OVERVIEW_URLS.items()
        }
        self.pages.update(pages or {})
        self.requested: list[str] = []

    async def get(self, url: str) -> str:
        self.requested.append(url)
        page = self.pages.get(url, fixture("challenge_no_results.html"))
        if isinstance(page, Exception):
            raise page

        return page

    async def aclose(self) -> None:
        pass


def settings(max_challenges: int) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@db/x",
        sync_max_challenges=max_challenges,
    )


async def stored_challenges(session_factory) -> dict[str, list[tuple[str, int, int | None]]]:
    async with session_factory() as session:
        challenges = await session.scalars(
            select(Challenge).options(
                selectinload(Challenge.results).selectinload(ChallengeResult.team)
            )
        )

        return {
            c.url: sorted(
                (r.team.display_name, r.place, None if r.score is None else int(r.score))
                for r in c.results
            )
            for c in challenges
        }


def expected_podium(html: str) -> list[tuple[str, int, int | None]]:
    return sorted((p.team_name, p.place, p.score) for p in parse_challenge(html))


def challenge_urls(fetcher: FakeFetcher) -> list[str]:
    return [url for url in fetcher.requested if url not in OVERVIEW_URLS.values()]


async def test_returns_result_and_logs_summary(session_factory, caplog):
    caplog.set_level(logging.INFO, logger="olympic_boinc.sync")

    result = await run_sync(session_factory, FakeFetcher(), settings(1))

    assert result.status == SyncStatus.OK
    assert (result.added, result.skipped, result.deferred, result.errors) == (0, 1, TOTAL - 1, [])
    assert result.finished_at is not None
    assert result.started_at <= result.finished_at
    assert f"sync ok in 0 s: added=0 skipped=1 deferred={TOTAL - 1} errors=0" in caplog.messages


async def test_collects_completed_challenges_from_both_overviews(session_factory):
    fetcher = FakeFetcher()

    result = await run_sync(session_factory, fetcher, settings(0))

    assert TOTAL == 205 + 861
    assert result.deferred == TOTAL
    assert fetcher.requested == list(OVERVIEW_URLS.values())


async def test_freshest_candidates_are_loaded_first(session_factory):
    fetcher = FakeFetcher()

    result = await run_sync(session_factory, fetcher, settings(3))

    assert challenge_urls(fetcher) == [c.url for c in FRESHEST[:3]]
    assert (result.skipped, result.deferred) == (3, TOTAL - 3)


async def test_stored_challenges_are_not_candidates(session_factory):
    async with session_factory() as session, session.begin():
        stored = FRESHEST[0]
        session.add(
            Challenge(
                challenge_type=stored.challenge_type,
                name=stored.name,
                start_at=stored.start_at,
                end_at=stored.end_at,
                url=stored.url,
            )
        )

    fetcher = FakeFetcher()

    result = await run_sync(session_factory, fetcher, settings(2))

    assert challenge_urls(fetcher) == [c.url for c in FRESHEST[1:3]]
    assert result.deferred == TOTAL - 3


async def test_saves_challenges_with_results(session_factory):
    first, second, third = FRESHEST[:3]
    team_page, project_page = fixture("challenge_results.html"), fixture("pchallenge_results.html")
    fetcher = FakeFetcher({first.url: team_page, second.url: project_page})

    result = await run_sync(session_factory, fetcher, settings(3))

    assert (result.status, result.added, result.skipped) == (SyncStatus.OK, 2, 1)

    stored = await stored_challenges(session_factory)

    assert stored == {
        first.url: expected_podium(team_page),
        second.url: expected_podium(project_page),
    }

    async with session_factory() as session:
        challenge = await session.scalar(select(Challenge).where(Challenge.url == first.url))

        assert (challenge.challenge_type, challenge.name, challenge.project_name) == (
            first.challenge_type,
            first.name,
            first.project_name,
        )
        assert (challenge.start_at, challenge.end_at) == (first.start_at, first.end_at)

        teams = await session.scalar(select(func.count()).select_from(Team))

        assert teams == len({name for podium in stored.values() for name, _, _ in podium})


async def test_teams_are_shared_between_challenges(session_factory):
    page = fixture("challenge_results.html")
    fetcher = FakeFetcher({FRESHEST[0].url: page, FRESHEST[1].url: page})

    result = await run_sync(session_factory, fetcher, settings(2))

    assert result.added == 2

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Team)) == len(
            expected_podium(page)
        )


async def test_duplicate_team_keeps_best_place(session_factory, caplog):
    page = fixture("challenge_results.html")
    first, second = (p.team_name for p in parse_challenge(page)[:2])
    page = page.replace(f">{second}<", f">{first}<")
    fetcher = FakeFetcher({FRESHEST[0].url: page})

    await run_sync(session_factory, fetcher, settings(1))

    podium = (await stored_challenges(session_factory))[FRESHEST[0].url]

    assert [place for name, place, _ in podium if name == first] == [1]
    assert "listed more than once" in caplog.text


async def test_broken_challenge_page_gives_partial(session_factory, caplog):
    page = fixture("challenge_results.html")
    fetcher = FakeFetcher(
        {
            FRESHEST[0].url: page,
            FRESHEST[1].url: "<html><body>changed</body></html>",
            FRESHEST[2].url: page,
        }
    )

    result = await run_sync(session_factory, fetcher, settings(3))

    assert (result.status, result.added, result.skipped) == (SyncStatus.PARTIAL, 2, 1)
    assert set(await stored_challenges(session_factory)) == {FRESHEST[0].url, FRESHEST[2].url}
    assert len(result.errors) == 1 and result.errors[0].startswith(
        f"{FRESHEST[1].url}: ParseError: "
    )
    assert result.errors[0] in caplog.messages
    assert any(
        r.levelno == logging.WARNING and r.message.startswith("sync partial")
        for r in caplog.records
    )


@pytest.mark.parametrize("challenge_type", list(ChallengeType))
async def test_blocked_overview_gives_failed(session_factory, challenge_type, caplog):
    url = OVERVIEW_URLS[challenge_type]
    fetcher = FakeFetcher({url: BlockedError(url, 403, "cloudflare challenge")})

    result = await run_sync(session_factory, fetcher, settings(3))

    assert result.status == SyncStatus.FAILED
    assert (
        result.errors[0] == f"{url}: BlockedError: status=403: cloudflare challenge"
    )  # the URL is not repeated
    assert challenge_urls(fetcher) == []
    assert await stored_challenges(session_factory) == {}
    assert any(
        r.levelno == logging.ERROR and r.message.startswith("sync failed") for r in caplog.records
    )


async def test_block_on_challenge_page_stops_the_run(session_factory):
    blocked = FRESHEST[1].url
    fetcher = FakeFetcher(
        {
            FRESHEST[0].url: fixture("challenge_results.html"),
            blocked: BlockedError(blocked, 200, "captcha"),
        }
    )

    result = await run_sync(session_factory, fetcher, settings(3))

    assert result.status == SyncStatus.PARTIAL
    assert challenge_urls(fetcher) == [FRESHEST[0].url, blocked]
    assert (result.added, result.skipped, result.deferred) == (1, 0, TOTAL - 1)
    assert set(await stored_challenges(session_factory)) == {FRESHEST[0].url}
    assert result.errors[0].startswith(f"{blocked}: BlockedError: ")


async def test_second_run_changes_nothing_and_loads_only_unsaved(session_factory):
    page = fixture("challenge_results.html")
    pages = {FRESHEST[0].url: page, FRESHEST[2].url: page}
    await run_sync(session_factory, FakeFetcher(pages), settings(3))
    before = await stored_challenges(session_factory)
    fetcher = FakeFetcher(pages)

    result = await run_sync(session_factory, fetcher, settings(3))

    assert await stored_challenges(session_factory) == before
    assert challenge_urls(fetcher) == [c.url for c in (FRESHEST[1], *FRESHEST[3:5])]
    assert (result.added, result.skipped) == (0, 3)


async def test_results_that_appear_later_are_saved(session_factory):
    url = FRESHEST[0].url
    first = await run_sync(session_factory, FakeFetcher(), settings(1))

    assert (first.added, first.skipped) == (0, 1)
    assert await stored_challenges(session_factory) == {}

    page = fixture("pchallenge_results.html")
    second = await run_sync(session_factory, FakeFetcher({url: page}), settings(1))

    assert second.added == 1
    assert await stored_challenges(session_factory) == {url: expected_podium(page)}
