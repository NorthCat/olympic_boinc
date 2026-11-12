# Spec Delta

## ADDED Requirements

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
