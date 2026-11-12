# Proposal

## Why

Data must update automatically once a day, without manual execution. We decided to embed the scheduler (APScheduler) in the application process: this requires no separate infrastructure (cron, systemd). This is the only way to start synchronization; `max_instances=1` prevents overlapping runs.

## What Changes

- A scheduler inside the FastAPI application starts synchronization according to a configured cron expression (once a day by default).
- Each run opens its own page fetcher (Chrome through nodriver) and closes it on completion; the browser does not run between synchronization runs.
- The scheduler starts and stops with the application. It can be disabled through a setting, for example in tests or with multiple replicas.
- A FastAPI application factory with lifespan is created. REST routers from `medals-rest-api` will be attached to it later.

## Capabilities

### New Capabilities
- `scheduled-sync`: automatic periodic challenge synchronization runs.

### Modified Capabilities

## Impact

- New modules: `src/olympic_boinc/scheduler.py`, `src/olympic_boinc/api/app.py` (`create_app` factory with lifespan).
- Dependency: apscheduler 3.x.
- Settings: `sync_cron`, `scheduler_enabled` (already declared in `project-foundation`).
- Uses `run_sync` from `challenge-sync` and `create_fetcher` from `boincstats-fetching`.
- Deployment: Chrome/Chromium and a display are required — the browser only works with a window; on a server, the application runs under Xvfb (`xvfb-run`).
