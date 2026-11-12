# Proposal

## Why

Synchronization summaries are currently visible only in the application's stderr and disappear when the terminal closes. When a run is interrupted by a BoincStats CAPTCHA, a single APScheduler “executed successfully” message does not explain what happened or how many requests reached the site. A persistent run log listing requested pages is needed to investigate such cases and tune request limits.

## What Changes

- Synchronization run log in `logs/sync.log` in the application working directory (project root). The path is set through `OLYMPIC_SYNC_LOG_FILE`.
- The log includes:
  - scheduler start and stop;
  - start and end of each run;
  - every request to BoincStats (URL, including retries);
  - challenge errors;
  - run summary line.
- The file rotates by size. Stderr output does not change.
- The log is maintained only when the scheduler is enabled.
- The scheduler job receives the name `sync` instead of the automatic `partial`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `scheduled-sync`: adds a requirement for a run log file.

## Impact

- `src/olympic_boinc/scheduler.py`, `src/olympic_boinc/api/app.py`, `src/olympic_boinc/scraper/fetcher.py`, `src/olympic_boinc/config.py`.
- New setting `OLYMPIC_SYNC_LOG_FILE` (default `logs/sync.log`); `logs/` is added to `.gitignore`.
- Documentation: `README.md`, `../../../../AGENTS.md`, `.env.example`.
