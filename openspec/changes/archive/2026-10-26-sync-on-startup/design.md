# Design

## Context

`build_scheduler` (`scheduler.py`) registers one `sync` job with `CronTrigger`, `max_instances=1`, and `coalesce=True`. Lifespan in `api/app.py` creates and starts the scheduler when `scheduler_enabled` and attaches the synchronization log. Requirements are in `specs/scheduled-sync/spec.md`.

## Goals / Non-Goals

**Goals:**
- The first run immediately on startup, without a second job or separate execution code.

**Non-Goals:**
- Manual execution (CLI, HTTP).
- Startup execution only “if it has not run for a long time”: there is no run history in the database.

## Decisions

- **`next_run_time` on the same job.** With `sync_on_startup`, the `sync` job is added with `next_run_time=datetime.now(UTC)`: APScheduler executes it immediately after `start()`, then takes the time from the cron trigger. Since this is the same job, `max_instances=1`, logging, and browser cleanup in `sync_job` work unchanged.
  - The alternative is a second one-shot job (`DateTrigger`). Rejected: two jobs have separate `max_instances`, and the startup run could execute in parallel with a scheduled run.
  - Another alternative is `asyncio.create_task(sync_job(...))` in lifespan. Rejected: it bypasses the scheduler, its overlap protection, and graceful shutdown.
- **Late execution.** APScheduler defaults `misfire_grace_time` to 1 s. The run time is computed in `build_scheduler`, and `start()` is called immediately afterward, so the run is not considered missed.
- **Setting** `sync_on_startup: bool = False` (`OLYMPIC_SYNC_ON_STARTUP`). It takes effect only inside `build_scheduler`, so it has no effect with the scheduler disabled.

## Risks / Trade-offs

- [Frequent restarts (failure with `Restart=on-failure` in systemd, restarts during debugging) produce extra site traversals and may trigger a BoincStats CAPTCHA] → disabled by default. README warning: enable for initial deployment or verification rather than keeping it enabled on an unstable service. Saved challenges are not fetched again, so an extra run primarily means extra requests to lists and challenges without results.
- [Restart shortly before a scheduled time] → the startup run is still in progress, so the scheduled run is skipped (`max_instances=1`); data are not corrupted.
