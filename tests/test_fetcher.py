from pathlib import Path

import pytest

from olympic_boinc.config import Settings
from olympic_boinc.scraper.fetcher import (
    BlockedError,
    FetchError,
    NodriverFetcher,
    TransientError,
    create_fetcher,
    is_captcha_page,
    is_cloudflare_challenge,
)

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://www.boincstats.com/stats/pchallenge/team/overview"
CHALLENGE_HTML = (FIXTURES / "cloudflare_challenge.html").read_text()
CAPTCHA_HTML = (FIXTURES / "captcha_challenge.html").read_text()
DATA_HTML = (FIXTURES / "pchallenge_overview.html").read_text()


class FakeClock:
    """Virtual time: `sleep` records the pause and advances `now`."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class ScriptedFetcher(NodriverFetcher):
    """Plays back a script of (status, html) pairs or exceptions instead of loading pages."""

    def __init__(self, script: list, delay: float = 0.0, retries: int = 3) -> None:
        self.clock = FakeClock()
        super().__init__(
            request_delay=delay, retries=retries, sleep=self.clock.sleep, clock=self.clock
        )
        self.script = script
        self.calls: list[str] = []

    async def _load(self, url: str) -> tuple[int, str]:
        self.calls.append(url)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item

        return item


def test_cloudflare_challenge_is_recognized():
    assert is_cloudflare_challenge(403, CHALLENGE_HTML)


def test_page_with_data_is_not_a_challenge():
    assert not is_cloudflare_challenge(200, DATA_HTML)
    assert not is_cloudflare_challenge(403, DATA_HTML)
    assert not is_captcha_page(DATA_HTML)


def test_captcha_page_is_recognized():
    assert is_captcha_page(CAPTCHA_HTML)


async def test_successful_fetch():
    fetcher = ScriptedFetcher([(200, DATA_HTML)])

    assert await fetcher.get(URL) == DATA_HTML
    assert fetcher.calls == [URL]


async def test_every_request_is_logged(caplog):
    caplog.set_level("INFO", logger="olympic_boinc.scraper.fetcher")
    fetcher = ScriptedFetcher([TransientError("timed out"), (200, DATA_HTML)])

    await fetcher.get(URL)

    assert [m for m in caplog.messages if m.startswith("GET ")] == [
        f"GET {URL}",
        f"GET {URL}",
    ]  # retries too


async def test_temporary_failure_is_retried():
    fetcher = ScriptedFetcher([TransientError("timed out"), (200, DATA_HTML)])

    assert await fetcher.get(URL) == DATA_HTML
    assert len(fetcher.calls) == 2


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_retryable_status_is_retried(status):
    fetcher = ScriptedFetcher([(status, ""), (200, DATA_HTML)])

    assert await fetcher.get(URL) == DATA_HTML
    assert len(fetcher.calls) == 2


async def test_retries_are_exhausted():
    fetcher = ScriptedFetcher([(502, "")] * 4, delay=1.0, retries=3)

    with pytest.raises(FetchError) as exc_info:
        await fetcher.get(URL)

    assert len(fetcher.calls) == 4
    assert exc_info.value.url == URL and exc_info.value.status == 502
    assert URL in str(exc_info.value) and "502" in str(exc_info.value)

    # Backoff pauses only (each exceeds the request delay, so throttling adds none) and they grow.
    sleeps = fetcher.clock.sleeps

    assert len(sleeps) == 3
    assert sleeps == sorted(sleeps) and sleeps[0] >= 2.0


async def test_network_errors_exhaust_retries():
    fetcher = ScriptedFetcher([TransientError("network error")] * 2, retries=1)

    with pytest.raises(FetchError) as exc_info:
        await fetcher.get(URL)

    assert exc_info.value.status is None
    assert "network error" in str(exc_info.value)


async def test_not_found_is_not_retried():
    fetcher = ScriptedFetcher([(404, "")])

    with pytest.raises(FetchError) as exc_info:
        await fetcher.get(URL)

    assert not isinstance(exc_info.value, BlockedError)
    assert exc_info.value.status == 404
    assert len(fetcher.calls) == 1


async def test_challenge_raises_blocked_error():
    fetcher = ScriptedFetcher([(403, CHALLENGE_HTML)])

    with pytest.raises(BlockedError) as exc_info:
        await fetcher.get(URL)

    assert exc_info.value.status == 403
    assert len(fetcher.calls) == 1


async def test_captcha_raises_blocked_error():
    fetcher = ScriptedFetcher([(200, CAPTCHA_HTML)])

    with pytest.raises(BlockedError, match="captcha"):
        await fetcher.get(URL)

    assert len(fetcher.calls) == 1


async def test_pause_between_requests():
    fetcher = ScriptedFetcher([(200, DATA_HTML)] * 3, delay=2.0)

    for _ in range(3):
        await fetcher.get(URL)

    # No wait before the first request; each next one waits out the whole delay.
    assert fetcher.clock.sleeps == [2.0, 2.0]


async def test_create_fetcher_uses_settings():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://u:p@db/x",
        request_delay=0.5,
        request_retries=5,
        browser_path="/usr/bin/chromium",
        browser_sandbox=False,
    )

    fetcher = create_fetcher(settings)

    assert isinstance(fetcher, NodriverFetcher)
    assert fetcher._throttle.delay == 0.5 and fetcher._retries == 5
    assert fetcher._browser_path == "/usr/bin/chromium" and fetcher._sandbox is False

    await fetcher.aclose()
