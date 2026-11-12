# Tasks

## 1. Log

- [x] 1.1 Setting `sync_log_file` (`OLYMPIC_SYNC_LOG_FILE`, default `logs/sync.log`), `logs/` in `.gitignore`, a line in `.env.example`. Verification: `Settings().sync_log_file == Path("logs/sync.log")`, `git check-ignore logs/sync.log` matches.
- [x] 1.2 The fetcher logs `GET <url>` before every fetch attempt. Verification: test `test_every_request_is_logged` — one retry produces two `GET` lines.
- [x] 1.3 `scheduler.py`: `open_sync_log(path)` / `close_sync_log(handler)` (`RotatingFileHandler` on synchronization loggers, directory created), `sync job started` line, job name `sync`. Verification: test `test_sync_log_file_gets_runs_and_urls` — the file contains run start, URL, and summary, no records from other loggers or records after closing; the trigger test checks the job name.
- [x] 1.4 Connect the log in lifespan only with the scheduler enabled; close it after scheduler shutdown, with the shutdown line. Verification: test `test_app_writes_sync_log_only_with_scheduler` — without the scheduler, no file; with the scheduler, the file contains `Scheduler started` and `Scheduler has been shut down`.

## 2. Documentation and verification

- [x] 2.1 Update `README.md` (“Settings” and “Logs” sections) and `../../../../AGENTS.md`. Verification: the log path, contents, and `OLYMPIC_SYNC_LOG_FILE` setting are described.
- [x] 2.2 Manual verification: `uvicorn` from the project root with cron set to the next minute and `OLYMPIC_SYNC_MAX_CHALLENGES=1`. Verification: `logs/sync.log` appears with run start, `GET` lines, and summary.
