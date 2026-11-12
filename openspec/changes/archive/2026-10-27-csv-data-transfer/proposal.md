# Proposal

## Why

Collected data can currently be transferred to another database (for example, a future container or server) only through a binary dump using `scripts/db_dump.py`. The dump replaces the entire database, cannot be read or edited manually, and cannot be added to a database that already contains data. Challenge history accumulates slowly from BoincStats (page limit per run, CAPTCHA), so it needs to be transferred without fetching from the site again. This requires a simple text format that can be opened in a spreadsheet editor and imported on top of existing data.

## What Changes

- Export all saved results to one CSV file: one row per podium placement. Each row contains challenge type, name, project, start and end dates, link, team, place, and score. The file contains no internal database identifiers.
- Import such a file into a database:
  - existing challenges (by link) are skipped, as in synchronization;
  - teams are matched by exact name, and missing teams are created;
  - the entire file is validated first; on any error, nothing is imported, and the report lists rows with errors;
  - the result is the number of added and skipped challenges.
- Commands run from the command line as a package module: `python -m olympic_boinc.csv_transfer export|import`. This also makes them available inside a future Docker image.
- The binary dump `scripts/db_dump.py` remains for full backups.

## Capabilities

### New Capabilities
- `data-transfer`: exporting saved results to CSV and importing them into a database, file format, and rules for merging with existing data.

### Modified Capabilities

## Impact

- New module `src/olympic_boinc/csv_transfer.py`. Saving a challenge with podium finishers is shared with synchronization: extract it from `sync.py` into a function available to both.
- No new dependencies: standard `csv` module.
- Tests: `tests/test_csv_transfer.py`.
- Documentation: `README.md`, `../../../../AGENTS.md`.
