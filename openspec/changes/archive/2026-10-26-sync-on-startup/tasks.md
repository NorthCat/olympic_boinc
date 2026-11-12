# Tasks

## 1. Implementation

- [x] 1.1 Setting `sync_on_startup` (`OLYMPIC_SYNC_ON_STARTUP`, default `false`) and a line in `.env.example`. Verification: `Settings(...).sync_on_startup is False`, and `true` from the environment is read.
- [x] 1.2 `build_scheduler`: with `sync_on_startup`, the `sync` job receives `next_run_time` = current UTC time; otherwise the time comes from cron. Verification: unit tests — with the setting, `next_run_time` is almost “now”; without it, it matches the next cron time; `max_instances=1` and a cron trigger in both cases.
- [x] 1.3 Integration test: the application with the scheduler and `sync_on_startup` enabled calls the job immediately after startup (`run_sync` and `create_fetcher` stubs), without the setting it does not; with the scheduler disabled, the job is not called. Verification: `pytest` passes.

## 2. Documentation and verification

- [x] 2.1 Update `README.md` (settings table, “Running”, warning about frequent restarts) and `../../../../AGENTS.md`. Verification: the setting and its behavior are described.
- [x] 2.2 Manual verification: `uvicorn` with `OLYMPIC_SYNC_ON_STARTUP=true` without contacting the site (nonexistent `OLYMPIC_BROWSER_PATH`). Verification: `logs/sync.log` contains `sync job started` and a run summary immediately after startup; the next job run follows cron.
