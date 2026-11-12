# Tasks

## 1. Application and scheduler

- [x] 1.1 Add apscheduler (3.x) to dependencies. Verification: `pip install -e .[dev]` passes, and `import apscheduler` works on Python 3.13.
- [x] 1.2 `api/app.py`: `create_app(settings)` factory with lifespan (engine and session factory in `app.state`, resource cleanup on shutdown). The fetcher is not stored in `app.state`: it is created for each synchronization run (see 1.3). Verification: a test starts the application through `httpx.AsyncClient` + `LifespanManager` without errors.
- [x] 1.3 `scheduler.py`: `build_scheduler(settings, job)` — `AsyncIOScheduler(timezone=UTC)`, `CronTrigger.from_crontab(sync_cron)`, `max_instances=1`, `coalesce=True`. On each run, the job creates a fetcher with `create_fetcher(settings)`, calls `run_sync`, and calls `await fetcher.aclose()` in `finally` (closes Chrome); an exception inside the job is logged and does not crash the scheduler. Verification: a unit test checks that the job is registered with the expected trigger and `max_instances=1`.
- [x] 1.4 Connect the scheduler in lifespan: start if `scheduler_enabled` is enabled; `shutdown(wait=False)` on shutdown. Verification: tests — with `scheduler_enabled=False`, the scheduler is not created; with `True`, it starts and stops with the application.

## 2. Verification

- [x] 2.1 Test: the scheduled job calls `run_sync` (replace `run_sync` with a stub, execute the job directly). Verification: the stub is called once; an exception in `run_sync` does not crash the scheduler; the fetcher's `aclose()` (substituted through `create_fetcher`) is called after both a successful run and an exception.
- [x] 2.2 Manual verification: `uvicorn` with `OLYMPIC_SYNC_CRON="*/5 * * * *"` and `OLYMPIC_SYNC_MAX_CHALLENGES=1` (to avoid loading the site) against the live site; the browser needs a display, on a server use `xvfb-run uvicorn ...`. Verification: run summaries appear in the log, runs do not overlap, and no Chrome process exists between runs.
