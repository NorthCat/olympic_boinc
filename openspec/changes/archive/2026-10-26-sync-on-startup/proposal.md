# Proposal

## Why

Synchronization runs only on schedule, by default once a day at 03:00 UTC. After initial deployment or changing settings, one has to wait for the next run or temporarily change cron for verification. We need an option to start synchronization immediately on application startup without changing the schedule.

## What Changes

- New setting `OLYMPIC_SYNC_ON_STARTUP` (default `false`). If enabled, synchronization runs immediately on application startup, then on schedule as usual.
- The startup run follows the same rules as scheduled runs:
  - does not overlap with other runs;
  - is written to the synchronization log;
  - the browser closes after completion.
- The setting has no effect when the scheduler is disabled.
- There is still no manual execution (CLI, HTTP).

## Capabilities

### New Capabilities

### Modified Capabilities
- `scheduled-sync`: adds a requirement for synchronization on application startup.

## Impact

- `src/olympic_boinc/config.py` (`sync_on_startup` setting), `src/olympic_boinc/scheduler.py` (first job run).
- Documentation: `.env.example`, `README.md`, `../../../../AGENTS.md`.
