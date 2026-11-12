"""Smoke tests against the real BoincStats site. Skipped by default; run with `pytest -m live`."""

import pytest

from olympic_boinc.config import get_settings
from olympic_boinc.scraper.fetcher import create_fetcher, is_cloudflare_challenge

pytestmark = pytest.mark.live

OVERVIEWS = [
    "https://www.boincstats.com/stats/pchallenge/team/overview",
    "https://www.boincstats.com/stats/challenge/team/overview",
]


async def test_configured_fetcher_loads_both_overviews():
    fetcher = create_fetcher(get_settings())

    try:
        for url in OVERVIEWS:
            html = await fetcher.get(url)

            assert 'id="tblChallenges"' in html
            assert not is_cloudflare_challenge(403, html)
    finally:
        await fetcher.aclose()
