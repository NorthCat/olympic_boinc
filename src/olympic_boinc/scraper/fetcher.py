import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

import nodriver
from nodriver.core.connection import ProtocolException
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from olympic_boinc.config import Settings

logger = logging.getLogger(__name__)

CHALLENGE_MARKERS = ("<title>Just a moment...</title>", "challenges.cloudflare.com", "cf-chl")
# BoincStats' own Shieldon firewall shows a reCAPTCHA page when requests come too often.
CAPTCHA_MARKERS = ("<title>Please solve Captcha</title>", "shieldon_captcha")


class FetchError(Exception):
    """A page could not be fetched; `status` is the last HTTP status (None for network errors)."""

    def __init__(self, url: str, status: int | None = None, reason: str = "") -> None:
        self.url = url
        self.status = status
        # Keep the detail separate so callers can avoid repeating the URL in logs.
        self.detail = f"status={status}" + (f": {reason}" if reason else "")
        super().__init__(f"{url}: {self.detail}")


class BlockedError(FetchError):
    """A challenge or captcha page (Cloudflare or BoincStats' firewall) came instead of content."""


class TransientError(Exception):
    """A network error or timeout while loading a page; the request is retried."""


class PageFetcher(Protocol):
    async def get(self, url: str) -> str: ...

    async def aclose(self) -> None: ...


def is_cloudflare_challenge(status: int, html: str) -> bool:
    return status in (403, 503) and any(marker in html for marker in CHALLENGE_MARKERS)


def is_captcha_page(html: str) -> bool:
    return any(marker in html for marker in CAPTCHA_MARKERS)


def _is_transient(exc: BaseException) -> bool:
    """Network errors, timeouts, 5xx and 429 are retried; blocks and other statuses are not."""
    if not isinstance(exc, FetchError) or isinstance(exc, BlockedError):
        return False

    return exc.status is None or exc.status == 429 or exc.status >= 500


class Throttle:
    """Keeps at least `delay` seconds between the starts of consecutive requests."""

    def __init__(
        self,
        delay: float,
        sleep: Callable[[float], Any] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.delay = delay
        self._sleep = sleep
        self._clock = clock
        self._last_start: float | None = None

    async def wait(self) -> None:
        if self._last_start is not None:
            remaining = self.delay - (self._clock() - self._last_start)
            if remaining > 0:
                await self._sleep(remaining)
        self._last_start = self._clock()


class NodriverFetcher:
    """Chrome driven over CDP by nodriver, which passes the Cloudflare managed challenge.

    Requests are throttled, transient failures are retried with backoff, challenge and captcha pages
    raise `BlockedError`. If Cloudflare shows a human-verification checkbox, it is clicked.
    The browser runs with a window: in headless mode the challenge does not pass,
    so a server needs a display (e.g. Xvfb). One browser is kept for all requests, so the
    `cf_clearance` cookie is reused.
    """

    def __init__(
        self,
        request_delay: float,
        retries: int = 3,
        browser_path: str | None = None,
        sandbox: bool = True,
        timeout: float = 60.0,
        sleep: Callable[[float], Any] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._retries = retries
        self._browser_path = browser_path
        self._sandbox = sandbox
        self._timeout = timeout
        self._sleep = sleep
        self._throttle = Throttle(request_delay, sleep, clock)
        self._browser: Any = None

    async def get(self, url: str) -> str:
        delay = self._throttle.delay
        retrying = AsyncRetrying(
            retry=retry_if_exception(_is_transient),
            stop=stop_after_attempt(self._retries + 1),
            wait=wait_exponential_jitter(initial=2 * delay, jitter=delay),
            sleep=self._sleep,
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

        return await retrying(self._fetch_once, url)

    async def _fetch_once(self, url: str) -> str:
        await self._throttle.wait()
        logger.info("GET %s", url)

        try:
            status, html = await self._load(url)
        except TransientError as exc:
            raise FetchError(url, None, str(exc)) from exc

        if is_cloudflare_challenge(status, html):
            raise BlockedError(url, status, "Cloudflare challenge")
        if is_captcha_page(html):
            raise BlockedError(url, status, "BoincStats captcha (too many requests)")
        if not 200 <= status < 300:
            raise FetchError(url, status)

        return html

    async def _load(self, url: str) -> tuple[int, str]:
        """Return HTTP status and HTML; raise TransientError on network errors and timeouts."""
        try:
            return await self._load_page(url)
        except ProtocolException as exc:
            # E.g. the tab's CDP session is gone after the challenge navigated the page.
            raise TransientError(f"browser error: {exc}") from exc

    async def _load_page(self, url: str) -> tuple[int, str]:
        if self._browser is None:
            self._browser = await nodriver.start(
                headless=False, browser_executable_path=self._browser_path, sandbox=self._sandbox
            )
        tab = await self._browser.get(url)
        # Cloudflare reloads the page after verification; wait for the final document.
        deadline = time.monotonic() + self._timeout
        # Give the challenge a few seconds to pass by itself before looking for the checkbox.
        next_click = time.monotonic() + 3

        while True:
            html = await tab.get_content()
            challenge = any(marker in html for marker in CHALLENGE_MARKERS)
            if not challenge and await tab.evaluate("document.readyState") == "complete":
                break
            now = time.monotonic()
            if now >= deadline:
                if challenge:
                    raise BlockedError(url, None, "Cloudflare challenge did not pass")

                raise TransientError(f"page did not load in {self._timeout:.0f}s")
            if challenge and now >= next_click:
                try:
                    # Locate the checkbox in a screenshot using OpenCV, then click it.
                    await tab.verify_cf()
                    logger.info("Clicked the Cloudflare checkbox on %s", url)
                except TypeError:
                    # verify_cf got no location: the screenshot or opencv was unavailable.
                    logger.warning("Could not look for the Cloudflare checkbox on %s", url)

                next_click = now + 5
            await tab.sleep(1)

        status = await tab.evaluate(
            "performance.getEntriesByType('navigation')[0]?.responseStatus ?? 0"
        )
        if not status:
            raise TransientError("network error")

        return status, html

    async def aclose(self) -> None:
        if self._browser is not None:
            self._browser.stop()
            self._browser = None


def create_fetcher(settings: Settings) -> PageFetcher:
    return NodriverFetcher(
        settings.request_delay,
        settings.request_retries,
        browser_path=settings.browser_path,
        sandbox=settings.browser_sandbox,
    )
