# Design

## Context

We use `PageFetcher` (`boincstats-fetching`), `parse_overview` (returns `list[ChallengeSummary]`) and `parse_challenge` (`challenge-parsing`), and models from `project-foundation`. The BoincStats overview shows all challenges on one page, without pagination. The fetcher maintains a `request_delay` between site requests (default 60 s): frequent requests cause the BoincStats firewall to show a CAPTCHA. Requirements are in `specs/challenge-sync/spec.md`.

## Goals / Non-Goals

**Goals:**
- One entry point `run_sync(session_factory, fetcher, settings) -> SyncResult`, called by the scheduler.

**Non-Goals:**
- Scheduling and prevention of overlapping runs (`scheduled-sync`).
- Manual execution (CLI, HTTP) and storing run history in the database.
- Updating already saved challenges: Completed results do not change.

## Decisions

- **Algorithm:**
  1. For `challenge_type` in (`project`, `team`), fetch and parse the overview page. Collect `ChallengeSummary`.
  2. Load the set of `url` values of already saved challenges from the database in one query.
  3. Candidates are challenges whose `url` is absent from the database. Sort by `end_at` descending and take the first `sync_max_challenges`; the rest are `deferred`.
  4. For each candidate: fetch the page, call `parse_challenge`. An empty podium finisher list means skip (`skipped`); otherwise save in a separate transaction (`session.begin()`). Add errors to the list and skip the challenge. `BlockedError` interrupts the loop: unprocessed candidates are added to `deferred`.
  5. Return `SyncResult` and log the summary.
- **`SyncResult`** (dataclass): `status`, `started_at`, `finished_at`, `added`, `skipped`, `deferred`, `errors: list[str]`. Not stored in the database.
- **Per-run limit** — setting `OLYMPIC_SYNC_MAX_CHALLENGES` (`sync_max_challenges`, default 100). With a 60 s delay, a run takes about 1.7 h; history (~1070 results pages) is loaded in about 11 daily runs, with recent challenges first.
- **Run status:**
  - `failed` — at least one overview page could not be fetched or parsed;
  - `partial` — errors in individual challenges or a run interrupted by blocking on a challenge page;
  - `ok` — no errors.
- **Team upsert:** `INSERT ... ON CONFLICT (display_name) DO NOTHING RETURNING id`; if the result is empty, `SELECT`.
- **Saving a challenge:** `INSERT ... ON CONFLICT (url) DO NOTHING RETURNING id`. If no row is inserted (the challenge was already saved concurrently), leave results untouched; otherwise `INSERT` podium finishers in the same transaction. Saved challenges do not change.
- **Duplicate team within a challenge** (one name occurs twice, unlikely) — take the best place and log a warning.
- **No database locks.** Runs do not overlap because only the scheduler starts them with `max_instances=1` (`scheduled-sync`). If this does happen (for example, multiple replicas), data are not corrupted: inserts use `ON CONFLICT DO NOTHING`.
- **Log:** run summary — one INFO line (status, duration, `added`/`skipped`/`deferred` counters); `failed` — ERROR, `partial` — WARNING. Challenge errors are written as `<url>: <type>: <message>` lines with tracebacks.

## Risks / Trade-offs

- [Challenges without results are not saved, so their pages are fetched on every run and occupy slots in the limit] → this is `N × 60 s` per day, where N is the number of such challenges. They cannot be distinguished from those not yet checked, so if N is comparable to the limit, history loading stops (in the log: `added` = 0, `skipped` grows). We would then revisit storing a skipped list with check dates.
- [Run history exists only in the application log] → a deliberate simplification. If viewing status through the API becomes necessary, we will revisit a run table.
- [History is not loaded immediately: ~11 days at a limit of 100] → recent challenges come first, so current standings appear from the first run. Progress is visible through `deferred` in the log; already saved data are not lost on interruption.
- [CAPTCHA or Cloudflare check midway through a run] → the run stops with status `partial`; the next run continues with remaining candidates.
- [If BoincStats ever corrects completed challenge results, we will not see it] → a deliberate compromise to save requests. For correction, a challenge can be deleted from the database — the next run fetches it again.
