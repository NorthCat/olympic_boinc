# Tasks

## 1. Preparation

- [x] 1.1 Check design.md against fixtures and the “Page structure” section from `boincstats-fetching`: selectors, ID source, place (column or position), date format, “no results” indicator. Update design.md and spec if anything differs. Verification: design.md contains no preliminary wording, and `openspec validate challenge-parsing --strict` passes.
- [x] 1.2 Add selectolax to dependencies, create `scraper/types.py` with `ChallengeSummary`, `TeamPlacement`, `ParseError`. Verification: `python -c "import olympic_boinc.scraper.types"` executes.

## 2. Overview parsing

- [x] 2.1 Implement `parse_overview`: `table#tblChallenges`, column lookup by headers, skipping rows without `<td>`, Completed filter, ID from the `team/list/{id}` link (project challenges) or `onclick="challengeChatShow({id})"` (team challenges), canonical URL `/stats/{type}/team/list/{id}/rank`. Verification: tests on `pchallenge_overview.html` (205 Completed out of 208, type `project`) and `challenge_overview.html` (861 Completed, type `team`); URLs of two challenges with the same name (“The Drive for Five”) differ.
- [x] 2.2 Parse period dates (`%Y-%m-%d %H:%M`) into UTC. Verification: a test compares dates of 2–3 challenges with page values, dates have `tzinfo=UTC`; challenges ending before they start (for example, 28795 ending on 1970-01-01) are returned with dates as on the page.

## 3. Challenge page parsing

- [x] 3.1 Implement `parse_challenge`: `table#tblStats`, `tr[id^="rank_"]` rows, name, score from “Total credit”; place from the Rank column, or competition ranking by score without it. Verification: tests on `challenge_results.html` (place from Rank) and `pchallenge_results.html` (place by score); podium finishers match the page.
- [x] 3.2 Recognize “no results” → `[]`. Verification: test on `challenge_no_results.html`.
- [x] 3.3 Support ties. Verification: tests on synthetic fixtures — edit the team challenge Rank column to (1, 1, 3) and (1, 2, 2), and use equal credit in a project challenge (1, 1, 3); all teams are returned with correct places.

## 4. Errors

- [x] 4.1 `ParseError` on a missing table or required columns. Verification: tests on truncated HTML, `cloudflare_challenge.html` and `captcha_challenge.html`, and a page without `table#tblStats` (simulated home page) — `ParseError` is raised and the message names the missing element.
