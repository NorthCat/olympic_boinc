# Proposal

## Why

Fetched BoincStats HTML must be converted into structured data: a list of completed challenges and the top three finishers in each. The parser is separate from fetching and storage, so it can be fully tested on saved fixtures and quickly fixed if BoincStats changes its markup.

## What Changes

- Parsing overview pages of both challenge types with a Completed status filter.
- Parsing an individual challenge page: teams in places 1–3, using the place from the page, or scores for project challenges (their page has no place column); ties are preserved.
- Recognizing a Completed challenge without results.
- An explicit parsing error on unexpected markup, so site changes do not turn into silent data loss.

## Capabilities

### New Capabilities
- `challenge-parsing`: extracting challenge information and podium placements from BoincStats HTML pages.

### Modified Capabilities

## Impact

- New modules: `src/olympic_boinc/scraper/parser.py`, `src/olympic_boinc/scraper/types.py`.
- Dependency: selectolax (or beautifulsoup4 + lxml; choice in design.md).
- Uses fixtures from `boincstats-fetching`. Depends on it: do not start the change without fixtures.
