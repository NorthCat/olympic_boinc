# rest-api Specification

## Purpose

A read-only HTTP API for clients (primarily a future frontend): Olympic-style team medal standings, challenges with podium finishers, and team information.

## Requirements

### Requirement: Medal standings
The system SHALL return a list of teams with at least one medal via `GET /api/medals`. For each team:
- identifier;
- name;
- number of gold medals (1st places);
- number of silver medals (2nd places);
- number of bronze medals (3rd places);
- total number of medals.

Sort order: by gold, then silver, then bronze — all descending; when all are equal, by team name ascending.

#### Scenario: Olympic sorting
- **WHEN** team A has 2 gold and 0 silver medals, and team B has 1 gold and 5 silver medals
- **THEN** team A ranks above team B in the standings

#### Scenario: Tie in a challenge
- **WHEN** two teams share 2nd place in a challenge
- **THEN** each receives one silver medal

### Requirement: Medal standings filters
`GET /api/medals` SHALL accept optional parameters:
- `challenge_type` = `project` | `team` | `all` (default `all`);
- `from`, `to` — ISO 8601 dates.

The `from` and `to` parameters limit the standings to challenges whose end date falls within the period (inclusive boundaries). An invalid parameter value SHALL result in a 422 response.

#### Scenario: Project challenges only
- **WHEN** `GET /api/medals?challenge_type=project` is requested
- **THEN** medals are counted only for project challenges

#### Scenario: Period
- **WHEN** `GET /api/medals?from=2025-01-01&to=2025-12-31` is requested
- **THEN** only challenges that ended in 2025 are included

#### Scenario: Invalid type
- **WHEN** `GET /api/medals?challenge_type=foo` is requested
- **THEN** the response is 422 with an error description

### Requirement: Challenge list
The system SHALL return challenges in descending order of end date via `GET /api/challenges`. For each challenge:
- identifier;
- type;
- name;
- project;
- period;
- BoincStats link;
- podium finishers (team, place, score).

The `challenge_type` filter and pagination with `page` (starting at 1) and `size` (default 50, maximum 200) are supported. The response includes the total number of records.

#### Scenario: Paginated output
- **WHEN** `GET /api/challenges?page=2&size=10` is requested
- **THEN** challenges 11 through 20 and the total number of challenges are returned

### Requirement: Individual challenge
The system SHALL return a challenge with its podium finishers via `GET /api/challenges/{id}`. If the challenge does not exist, the response SHALL be 404.

#### Scenario: Nonexistent challenge
- **WHEN** a challenge with a nonexistent identifier is requested
- **THEN** the response is 404

### Requirement: Team card
The system SHALL return the team name, its medals (gold, silver, bronze, total), and a list of challenges in which it earned a podium placement, with the place specified, via `GET /api/teams/{id}`. If the team does not exist, the response SHALL be 404.

#### Scenario: Team medals
- **WHEN** the card of a team with two gold medals is requested
- **THEN** the response contains gold = 2 and two challenges with place 1

### Requirement: Health check
The system SHALL respond to `GET /health` with 200 if the application is running and the database is available, and 503 if the database is unavailable.

#### Scenario: Database available
- **WHEN** `GET /health` is performed while the database is available
- **THEN** the response is 200

### Requirement: Challenge year list
The system SHALL return a JSON array of unique integer end-date years of all saved challenges in UTC, in descending order, for example `[2026, 2025, 2023]`, via `GET /api/challenges/years`. The response SHALL include both challenge types, be independent of challenge list pagination, and reflect saved data at request time. If there are no challenges, the response SHALL be `200` with `[]`. The “За весь период” value is a UI choice and MUST NOT be included in the API array. The endpoint SHALL be read-only and present in OpenAPI.

#### Scenario: List from data
- **WHEN** challenges of both types end in 2025, 2026, and again in 2025
- **THEN** `GET /api/challenges/years` returns `200` and `[2026, 2025]`

#### Scenario: Year in UTC
- **WHEN** a challenge end time corresponds to `2025-12-31T23:30:00Z` and the PostgreSQL session uses another time zone
- **THEN** the year of this challenge in the response is 2025

#### Scenario: Empty database
- **WHEN** there are no saved challenges
- **THEN** the endpoint returns `200` and `[]`

#### Scenario: Completeness and updates
- **WHEN** a challenge with a previously absent year is added, regardless of the number of `/api/challenges` pages
- **THEN** the next `/api/challenges/years` request includes the new year without a configuration update

#### Scenario: Routing
- **WHEN** a client requests `/api/challenges/years` and then an existing challenge `/api/challenges/{id}`
- **THEN** the first request returns years without an identifier conversion error, and the second retains its previous behavior
