# Design

## Context

The HTML structure is known from the spike in `boincstats-fetching`: the “Page structure” section in `openspec/changes/archive/2026-10-01-boincstats-fetching/design.md` and fixtures in `tests/fixtures/`: `pchallenge_overview.html`, `challenge_overview.html`, `pchallenge_results.html`, `challenge_results.html`, `challenge_no_results.html`, `cloudflare_challenge.html`, `captcha_challenge.html`. Fixtures are HTML after JS execution in the browser (as returned by `NodriverFetcher`). Requirements are in `specs/challenge-parsing/spec.md`.

## Goals / Non-Goals

**Goals:**
- Pure functions without I/O: HTML in, dataclasses out. Everything is tested on fixtures.
- Site markup changes → an explicit error rather than silent data loss.

**Non-Goals:**
- Page fetching (done by sync). Database persistence.

## Decisions

- **Types** (`scraper/types.py`, frozen dataclasses):
  - `ChallengeSummary(challenge_type, name, project_name, start_at, end_at, url)`;
  - `TeamPlacement(team_name, place, score)`.
- **Functions:**
  - `parse_overview(html, challenge_type, base_url) -> list[ChallengeSummary]`;
  - `parse_challenge(html) -> list[TeamPlacement]`;
  - `ParseError(msg)`.
- **Library — selectolax (Lexbor).** It is fast and understands CSS selectors. The alternative is BeautifulSoup + lxml: more tolerant of broken HTML, but slower. If fixtures prove severely invalid, we will switch to it.
- **Find columns by header text** (`<th>`), rather than index. This lets the parser tolerate reordered columns. Headers are compared ignoring whitespace and case: they contain `&nbsp;` (“Participants”) and `<br>` (“Total<br>credit”). Cell indexes account for `colspan`: in the project overview, “Team stats” and “User stats” each occupy two columns. A repeated header points to the first column. A missing required header causes `ParseError`.
- **Overview** — `table#tblChallenges`, all challenges in one table, no pagination. Required columns: Name, Project, Start time, End time, Status (team challenges also have Issued by and Participants; project challenges have Team stats and User stats; these are not needed). Skip rows without `<td>`: the team overview contains an advertising row `<tr class="static"><th colspan="7" class="tableAd">`.
- **Challenge ID:** for project challenges, from the `/stats/pchallenge/team/list/{id}/rank` link in the Team stats column; team challenges have no links, so the ID is taken from `onclick="challengeChatShow({id})"` on `<tr>`. If a Completed row has no ID, raise `ParseError`.
- **The challenge URL is its storage key**, so we build it from the type and ID rather than taking the link as is: `urljoin(base_url, "/stats/{pchallenge|challenge}/team/list/{id}/rank")`. This is the results page parsed by `parse_challenge`. One name can occur with different IDs (for example, “The Drive for Five”: 1 and 332); these are different challenges.
- **Status** is compared with `"completed"` ignoring case and surrounding whitespace (the cell value has surrounding spaces). Fixtures contain Completed and Upcoming.
- **Dates:** format `%Y-%m-%d %H:%M` (the value is inside `<nobr>` for team challenges), always UTC. The overview does not label the time zone, but the same dates on the challenge page are marked “UTC”, and server time is also UTC. The result is a `datetime` with `tzinfo=UTC`. Dates are not corrected (user decision): 4 project challenges end before they start, two of them on 1970-01-01 00:00 (28795, 28786); they are returned as is.
- **Results page** (`/stats/{type}/team/list/{id}/rank`): `table#tblStats`. Headers come from the first row of its first `<thead>`. After JS, floatThead moves the original header to a separate table without an id before `table#tblStats`, leaving a `size-row` with empty `<th>` in its place: header text remains only in `aria-label`, so if `<th>` has no text, use `aria-label` (in HTML without JS, the text is in `<th>` itself). The second `<thead>` after `<tbody>` (`header center top`) is not used: for project challenges it incorrectly labels the second column “Rank”, although it contains Total credit. Team rows are `tr[id^="rank_"]`; the first service row of `<tbody>` without an id is not parsed.
  - Team name — first cell text, trimming only surrounding whitespace (teams are not normalized).
  - Score — “Total credit” column (repeated twice for project challenges; use the first): remove thousands separators `,`, yielding an `int`.
  - **Place:** if a Rank column exists (team challenges), take the number from it. Otherwise (project challenges), calculate from scores: rows are in descending Total credit order, place = competition ranking (“1,1,3”), equal scores yield the same place. The number from `id="rank_N"` is not used for place: an id is unique and cannot express a tie.
  - The first 100 teams are shown, which is sufficient for the podium.
- **“No results”:** `table#tblStats` exists but contains no `rank_N` rows (as in Completed challenge 1135 with “Total number of teams: 12”) → empty list. No `table#tblStats` itself → `ParseError`. This also rejects unrelated pages: BoincStats returns 200 with the home page for a nonexistent URL, rather than 404; the fetcher rejects Cloudflare and CAPTCHA pages earlier, but the parser also raises `ParseError` for them.

## Risks / Trade-offs

- [Real data do not show how BoincStats displays ties (equal Rank for team challenges, equal credit for project challenges)] → synthetic fixtures made by editing real ones; the project challenge rule (competition ranking by score) is defined by us.
- [BoincStats may change markup] → `ParseError` plus `partial`/`failed` status in the synchronization log make breakage visible; fixture tests locate the problem.
- [Overview may contain statuses absent from fixtures (for example, for a running challenge)] → the filter allows only Completed; other statuses are discarded without error.
