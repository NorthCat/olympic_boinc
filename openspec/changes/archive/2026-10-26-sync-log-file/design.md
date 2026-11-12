# Design

## Context

Logging is configured by lifespan in `api/app.py` (`logging.basicConfig` to stderr). `run_sync` writes the run summary to the `olympic_boinc.sync` logger, tenacity logs request retries to `olympic_boinc.scraper.fetcher`, and `apscheduler` loggers record the job lifecycle. There are no separate records for every request to the site. Requirements are in `specs/scheduled-sync/spec.md`.

## Goals / Non-Goals

**Goals:**
- One file from which the progress of any run can be reconstructed.

**Non-Goals:**
- REST API and uvicorn logs in this file.
- Structured format (JSON), sending logs to external systems.
- Configurable level and rotation.

## Decisions

- **A separate handler on synchronization loggers.** `RotatingFileHandler` is attached to the `apscheduler`, `olympic_boinc.scheduler`, `olympic_boinc.sync`, and `olympic_boinc.scraper` loggers rather than the root logger. This puts only synchronization in the file while leaving stderr unchanged (loggers continue propagating records to the root). The alternative — `logging.config.dictConfig` with a configuration file — is excessive for one handler.
- **INFO level.** If a logger's effective level is higher than INFO, it is lowered to INFO; otherwise `GET <url>` lines will not reach the file when the root logger is unconfigured.
- **Size-based rotation:** 10 MB, 5 archive files, through standard `RotatingFileHandler`. A run produces about 50 lines per day, so the limit covers months. Time-based rotation is unnecessary.
- **Request logging in the fetcher.** A `GET <url>` line is written before every fetch attempt, after the delay, so retries are visible separately and the line time is the actual request time.
- **Run start** — a `sync job started` line in `sync_job`. The end is the `run_sync` summary line and the APScheduler job completion message.
- **Path relative to the working directory.** `Path("logs/sync.log")` resolves from the current directory, as does `.env`. When running from the project root or through systemd with `WorkingDirectory`, the file resides in `<root>/logs/`. Resolving relative to the package location is unsuitable: with a regular (non-editable) installation, it would be the site-packages directory.
- **Attachment in lifespan,** only when the scheduler is enabled. On shutdown, the handler is removed and closed so repeated `create_app` calls (tests) do not accumulate handlers.
- **Scheduler shutdown.** `AsyncIOScheduler.shutdown()` performs shutdown on the next event loop iteration. Before closing the file, lifespan yields one step to the loop (`asyncio.sleep(0)`) so the shutdown line reaches the log.
- **Job name `sync`.** Without an explicit name, APScheduler names the job after the callable, which is `functools.partial`. The log would contain `Running job "partial ..."`.

## Risks / Trade-offs

- [Running outside the project root creates `logs/` in another directory] → the path is set through `OLYMPIC_SYNC_LOG_FILE` and can be absolute. README states that `.env` and the log are resolved from the working directory.
- [Multiple application instances in one directory write to the same file, and rotation is not synchronized between processes] → the scheduler should already be enabled on only one instance. Other instances do not open the log.
