"""Fetch BoincStats pages using service settings from .env to refresh test fixtures.

Usage:
    python scripts/spike_fetch.py [--save DIR] [URL_OR_PATH ...]

Without URLs, fetches both challenge overview pages. Prints <title> and the number of tables;
with --save writes the HTML.
"""

import argparse
import asyncio
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from olympic_boinc.config import get_settings
from olympic_boinc.scraper.fetcher import create_fetcher

BASE_URL = "https://www.boincstats.com"
OVERVIEWS = ["/stats/pchallenge/team/overview", "/stats/challenge/team/overview"]


def summarize(url: str, html: str) -> str:
    title = re.search(r"<title>(.*?)</title>", html, re.S | re.I)

    return (
        f"{url}\n  bytes={len(html)} title={title.group(1).strip() if title else None!r}"
        f" tables={html.lower().count('<table')}"
    )


def file_name(url: str) -> str:
    path = urlparse(url).path.strip("/").replace("/", "_") or "index"

    return f"{path}.html"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("urls", nargs="*", default=OVERVIEWS)
    parser.add_argument("--save", type=Path, help="directory to write fetched HTML into")
    args = parser.parse_args()

    fetcher = create_fetcher(get_settings())

    try:
        for url in (urljoin(BASE_URL, u) for u in args.urls):
            html = await fetcher.get(url)
            print(summarize(url, html))
            if args.save:
                args.save.mkdir(parents=True, exist_ok=True)
                (args.save / file_name(url)).write_text(html, encoding="utf-8")
    finally:
        await fetcher.aclose()


if __name__ == "__main__":
    asyncio.run(main())
