# Design

## Context

Verified on 28.09.2026: `curl` with a browser User-Agent and WebFetch receive HTTP 403 with the Cloudflare “Just a moment…” page (`challenges.cloudflare.com`) from both overview pages. The HTML structure is therefore still unknown. Requirements are in `specs/page-fetching/spec.md`.

## Goals / Non-Goals

**Goals:**
- Obtain a working fetching method and real fixtures before starting to write the parser.
- Isolate fetching behind an interface so the method can be changed without touching the rest of the code.

**Non-Goals:**
- Solving BoincStats firewall reCAPTCHA and paid CAPTCHA-solving services. (We automatically check the Cloudflare “Verify you are human” checkbox — user decision of 01.10.2026, see Decisions.)
- Parsing. It is in `challenge-parsing`.

## Decisions

- **`PageFetcher` protocol** with methods `async get(url) -> str` and `aclose()`. Errors: `FetchError(url, status)` and its subclass `BlockedError`. Sync and tests depend only on the protocol; tests use `FakeFetcher`, which returns fixtures.
- **Delay, retries, and blocking detection** are in `NodriverFetcher.get` around a single attempt `_load(url) -> (status, html)`. An attempt reports network errors and timeouts through a `TransientError` exception. The logic is tested without a browser using a subclass that replaces `_load` with a response scenario. There is no separate base class: there is only one implementation.
- **`NodriverFetcher` is the only fetching method.** Cloudflare blocks curl_cffi and Playwright (see “Page structure”). nodriver controls regular Chrome through CDP, without WebDriver or automation indicators. The browser runs with a window: the challenge does not pass in headless mode, so a server needs a virtual display (Xvfb). One browser instance is used for all requests in a run to reuse the `cf_clearance` cookie. After navigation, we wait for challenge markers to disappear and `document.readyState` to become `complete`: without the second condition, the HTML is retrieved before it finishes loading. HTTP status is taken from `performance.getEntriesByType('navigation')[0].responseStatus`; 0 means a network error.
- **Python 3.13:** nodriver does not support 3.14, so the entire project was moved to 3.13 (venv `~/.pyenv/versions/olympic-boinc`).
- **Browser settings:** `OLYMPIC_BROWSER_PATH` (path to Chrome/Chromium; nodriver searches automatically by default) and `OLYMPIC_BROWSER_SANDBOX` (default `true`; `false` is needed for Chromium without an AppArmor profile, for example not installed from a .deb package). There is no fetching method selection in the configuration: there is only one method.
- **How blocking is detected:** Cloudflare — status 403 or 503 together with body markers: `<title>Just a moment...</title>`, `challenges.cloudflare.com`, `cf-chl`; a challenge that does not pass within the wait timeout also counts as blocking. BoincStats firewall CAPTCHA (Shieldon) — markers `<title>Please solve Captcha</title>`, `shieldon_captcha` with any status. Both produce `BlockedError` without retries.
- **Cloudflare “Verify you are human” checkbox** (user decision): if the challenge has not passed automatically 3 s after loading, locate the checkbox in a screenshot and click it, no more often than once every 5 s, until the wait timeout expires. We use nodriver's built-in `Tab.verify_cf`: the checkbox is hidden in a closed shadow root and a cross-origin iframe, so it finds it in a screenshot by template matching (requires opencv-python-headless) and clicks the mouse. Accepted limitations: it clicks the best match even if no checkbox is on screen, does not account for `devicePixelRatio` (it is 1 on a server with Xvfb), and temporarily writes `screen.jpg` and `cf_template.png` to the current directory; if screenshots or opencv are unavailable, it fails with `TypeError`, which we catch and log.
- **Browser errors:** nodriver `ProtocolException` during fetching (for example, when the tab's CDP session disappears after the challenge reloads the page) is treated as a temporary error and retried.
- **Rate limiting:** the fetcher stores the time of the last request; before a new request, we wait with `asyncio.sleep` until `request_delay` has elapsed (default 60 s: with a 2 s delay, the BoincStats firewall showed a CAPTCHA after a few dozen pages). Requests are sequential, without parallelism.
- **Retries** use tenacity (`AsyncRetrying`): exponential backoff `wait_exponential_jitter` with an initial delay of `2 * request_delay` and jitter up to `request_delay`; up to `request_retries` retries (default 3, setting `OLYMPIC_REQUEST_RETRIES`); timeouts, network errors, 5xx, and 429 are retried.
- **Spike** — script `scripts/spike_fetch.py`: fetches pages through `create_fetcher` with settings from `.env` and saves HTML. Also used to update fixtures.

## Page structure

- curl_cffi 0.16.3 (30.09.2026): both overview pages return 403 “Just a moment...” with `impersonate` = `chrome`, `chrome136`, `chrome131_android`, `safari184`, `firefox135`, `edge101`, including with a new session. Cloudflare requires JS execution; passive fingerprint checking is insufficient.
- Playwright 1.63.0 (01.10.2026): both overview pages return 403 “Just a moment...” and do not pass after 30–40 s of waiting. Tested headless shell, full Chromium in the new headless mode (`channel="chromium"`, `--disable-blink-features=AutomationControlled`, hidden `navigator.webdriver`, regular User-Agent), and Chromium with a window. The challenge type is `cType: 'managed'` with Turnstile.
- **Working fetching method** (01.10.2026): nodriver 0.50.3 + Chromium with a window. The first challenge passes in 4–40 s; subsequent pages load immediately. nodriver in headless mode is blocked.
- **Second protection layer — Shieldon.** After a few dozen page fetches over ~30 minutes, BoincStats started returning a “Please solve Captcha / Unusual behavior detected” page with reCAPTCHA (fixture `captcha_challenge.html`). This is site-side IP rate limiting; its exact limits and blocking duration are unknown.
- **Nonexistent URL:** BoincStats returns 200 with the home page (title “Home | BOINCstats/BAM!”) rather than 404. The parser must verify that it received the expected page.
- **Project challenge overview** (`/stats/pchallenge/team/overview`, fixture `pchallenge_overview.html`): one `table#tblChallenges` table, all challenges at once (208 rows), no pagination. Columns: Name, Project, Start time, End time, Team stats, User stats, Status. “Team stats” contains links `/stats/pchallenge/team/list/{id}/credits` and `/stats/pchallenge/team/list/{id}/rank`; Upcoming has `-` instead of links. One name may occur several times with different IDs (for example, “The Drive for Five”: 1 and 332).
- **Team challenge overview** (`/stats/challenge/team/overview`, fixture `challenge_overview.html`): `table#tblChallenges`, 862 rows, no pagination. Columns: Name, Project, Issued by, Start time, End time, Participants, Status. No links: the ID is in `onclick="challengeChatShow({id})"` on `<tr>`. The table contains a service advertising row `<tr class="static"><th colspan="7" class="tableAd">` without `<td>`.
- **Statuses:** fixtures contain `Completed` and `Upcoming` (with surrounding spaces in the cell). Other values (for example, for a running challenge) were not encountered at capture time.
- **Dates:** format `YYYY-MM-DD HH:MM`, without a time zone in the overview (inside `<nobr>` for team challenges). On the challenge page, the same dates are marked `UTC`, and server time is also UTC — we treat them as UTC.
- **Challenge URL and ID:** the ID is an integer, with a separate namespace for each type. Results page: `/stats/pchallenge/team/list/{id}/rank` and `/stats/challenge/team/list/{id}/rank` (the `/credits` variants in fixtures give the same credit sorting). Team challenges also have a `/stats/challenge/team/chat/{id}` page with a challenge card (Name, Status, Project, Issued by, dates with UTC, team count) and the same `table#tblChallengeStat` results table with Team Name, Rank, Credit columns.
- **Results table** on the `team/list/{id}/rank` page (fixtures `pchallenge_results.html`, `challenge_results.html`): `table#tblStats`; headers in `<thead>`, and the first `<tbody>` row is an empty service row (a header clone from floatThead). Team rows are `<tr id="rank_{N}">`; the team name is the text of the first `<td>` (as on the site). Columns differ: team challenges have Team Name, Total credit, Rank (`<a name="N"></a>N`), -1:00 … -32:00, Options; project challenges have no Rank column (the “Total credit” header appears twice), and the place exists only in `id="rank_N"` and `<a name="N">` in the second cell. The fixtures do not show how ties (equal credit) appear on the page — this is addressed in `challenge-parsing`. The first 100 teams are shown (“Teams: 1 - 100”), which is sufficient for the podium.
- **“No results”** (fixture `challenge_no_results.html`, team challenge 1135 with Completed status): the header says “Total number of teams: 12”, but `table#tblStats` contains only the service row, with no `rank_N` rows. No example of a project challenge without results was found.

## Risks / Trade-offs

- [Cloudflare blocks the fetching method, for example with an interactive Turnstile CAPTCHA] → `BlockedError` in the synchronization log. Discuss with the user: residential proxy, manual transfer of the `cf_clearance` cookie, manual HTML export.
- [Shieldon shows a CAPTCHA for frequent requests; limits are unknown] → default delay between requests is 60 s. Initial loading (≈1070 results pages) takes ≈18 h with this delay; how to split it is addressed in `challenge-sync`.
- [Cloudflare may tighten protection at any time] → `BlockedError` is recorded separately in the synchronization log; fetching is isolated behind `PageFetcher`.
- [The browser is heavy: Chrome occupies hundreds of MB and consumes RAM; a display is required] → the browser starts once per synchronization run and closes afterward; Xvfb on the server.
- [nodriver requires Python 3.13 and may lag behind new Python versions] → isolated behind `PageFetcher`; if problems arise, the method changes without modifying the rest of the code.
