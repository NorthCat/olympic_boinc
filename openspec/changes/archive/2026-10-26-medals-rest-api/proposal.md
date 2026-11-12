# Proposal

## Why

The project's goal is to show how many times each team took 1st, 2nd, and 3rd places in BoincStats challenges. Data are already collected and stored; a REST API is needed for a future frontend (and any clients) to obtain medal standings and challenges with podium finishers.

## What Changes

- Olympic-style medal standings with filters by challenge type and period.
- A list of challenges with podium finishers (with pagination) and an individual challenge.
- Team card: its medals and challenges in which it earned a podium placement.
- Health check.

## Capabilities

### New Capabilities
- `rest-api`: a read-only HTTP API serving medal standings, challenges, and teams.

### Modified Capabilities

## Impact

- New modules: `src/olympic_boinc/api/{schemas,deps}.py`, `src/olympic_boinc/api/routers/{medals,challenges,teams,health}.py`, `src/olympic_boinc/queries.py`.
- Routers connect to `create_app` from `scheduled-sync`.
- `../../../../AGENTS.md`: architecture and server startup.
