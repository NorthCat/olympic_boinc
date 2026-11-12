# Tasks

## 1. Synchronization service

- [x] 1.1 `sync.py`: `SyncResult`, `run_sync(session_factory, fetcher, settings)`, summary logging. Verification: a test returns `SyncResult` with counters after a run, and the log (`caplog`) contains a summary line.
- [x] 1.2 Fetch and parse overview pages of both types. Verification: a fixture-based test with `FakeFetcher` collects all Completed challenges from both pages.
- [x] 1.3 Select candidates: challenges whose `url` is absent from the database, by `end_at` descending, up to `sync_max_challenges` (setting `OLYMPIC_SYNC_MAX_CHALLENGES`, default 100). Verification: unit tests — saved challenges are excluded; when the limit is below the candidate count, the newest are selected and the rest counted in `deferred`.
- [x] 1.4 Save a challenge in a separate transaction: team upsert by `display_name`, challenge `INSERT ... ON CONFLICT (url) DO NOTHING`, podium finisher insertion; a challenge without podium finishers is not saved. Verification: after sync, database challenges, teams, and podium finishers match the fixtures; the challenge without results is absent.
- [x] 1.5 Error handling: skip a challenge with an error, `partial`/`failed` according to design.md, errors in `SyncResult.errors` and the log. Verification: tests — a broken challenge page yields `partial`, with others saved; `BlockedError` on an overview yields `failed` without data changes; `BlockedError` on a challenge page interrupts the run with status `partial`, subsequent pages are not requested from `FakeFetcher`, and unprocessed candidates are counted in `deferred`.

## 2. Integration verification

- [x] 2.1 Idempotency test: two consecutive runs — the second does not change data and requests only overview pages and unsaved challenge pages from `FakeFetcher`. Verification: `pytest` passes.
- [x] 2.2 Test for results appearing later: first run — page without results, challenge skipped; second — results appear, challenge and podium finishers saved. Verification: `pytest` passes.
- [x] 2.3 Live `run_sync` (one-off script `python -c "..."`) against BoincStats on the local database with `OLYMPIC_SYNC_MAX_CHALLENGES=3` to avoid loading the site; manually compare 2–3 challenges with the site. Verification: status `ok` or `partial` with clear reasons, data match the site.
