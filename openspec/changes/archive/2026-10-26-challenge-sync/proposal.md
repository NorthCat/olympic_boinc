# Proposal

## Why

The fetcher and parser exist, but they need to be connected to storage: traverse both challenge lists, fetch results for new completed challenges, and save podium finishers. The process will run daily, so it must be idempotent, economical in requests to BoincStats, and tolerant of failures in individual challenges.

## What Changes

- Synchronization service: fetches overview pages for both types, selects new Completed challenges, fetches and parses their pages, and saves results.
- Challenge page limit per run (newest first): BoincStats limits request rates, so history is loaded over several daily runs. Blocking (CAPTCHA, Cloudflare) interrupts the run.
- Challenges without results or with errors are not saved and are checked again on the next run.
- Each run summary (status, counters, errors) is written to the application log; run history is not stored in the database.
- Only the scheduler (`scheduled-sync`) starts synchronization; there is no manual trigger.

## Capabilities

### New Capabilities
- `challenge-sync`: synchronization of completed challenges and their podium finishers from BoincStats to local storage.

### Modified Capabilities

## Impact

- New module: `src/olympic_boinc/sync.py`.
- Uses `page-fetching`, `challenge-parsing`, and `data-model`.
