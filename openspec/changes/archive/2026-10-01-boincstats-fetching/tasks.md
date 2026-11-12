# Tasks

## 1. Spike: access verification and fixture collection

- [x] 1.1 Install curl_cffi in the venv and write `scripts/spike_fetch.py`: fetches both overview pages (`/stats/pchallenge/team/overview`, `/stats/challenge/team/overview`) with `impersonate="chrome"`. Verification: the script prints status and `<title>`, and the obtained HTML contains a challenge table. (Result: curl_cffi is blocked by Cloudflare and was removed from the project; the script was rewritten to use `create_fetcher`.)
- [x] 1.2 If 1.1 encounters blocking, retry through a browser (Playwright is blocked; use nodriver; the project was moved to Python 3.13). Record which method worked in design.md (“Page structure”). Verification: HTML for both overview pages is obtained. **Stop condition:** if all methods are blocked, stop work and discuss the options from design.md with the user.
- [x] 1.3 Save fixtures in `tests/fixtures/`: `pchallenge_overview.html`, `challenge_overview.html`, one project and one team challenge page with results, a Completed challenge without results, a second overview page (if pagination exists). Verification: files are present, and none contain Cloudflare markers.
- [x] 1.4 Document page structure in design.md: columns and status values, date format and time zone, challenge URL template and ID, pagination, results table and place column, “no results” indicator. Verification: the section is filled in, with no _TBD_ remaining.

## 2. Fetcher implementation

- [x] 2.1 Define the `PageFetcher` protocol, `FetchError` and `BlockedError` exceptions, and `is_cloudflare_challenge(status, html)` function in `scraper/fetcher.py`. Verification: detection unit test on a Cloudflare page and a fixture with data.
- [x] 2.2 Implement delays between requests, retry backoff, and `BlockedError` for a Cloudflare challenge and BoincStats CAPTCHA in `NodriverFetcher.get`. Verification: unit tests with a substituted `_load` cover spec scenarios (temporary failure, exhausted retries, 404 without retries, blocking, delay between requests).
- [x] 2.3 Implement page fetching in `NodriverFetcher._load`: a shared browser instance, waiting for the challenge to disappear and the page to finish loading, HTTP status from Navigation Timing, `browser_path` and `browser_sandbox` settings. Verification: a test marked `live` fetches an overview page (skipped by default).
- [x] 2.4 The `create_fetcher(settings)` factory creates `NodriverFetcher` with configuration settings. Verification: unit test for passing settings.
- [x] 2.5 A live smoke test (`live` marker, run with `pytest -m live`) fetches both overview pages. Verification: the test passes manually.
- [x] 2.6 Automatically check the Cloudflare “Verify you are human” checkbox through nodriver's `Tab.verify_cf`, treat CDP errors as temporary, and increase the default delay to 60 s. Verification: the live smoke test passes.
