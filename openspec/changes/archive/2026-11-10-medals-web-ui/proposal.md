# Proposal

## Why

The service already calculates medal standings through REST, but users need a simple way to view them in a browser and select a year and challenge type. The UI must use existing calculations, and the list of available years must use real data without manual updates.

## What Changes

- Add a Russian-language `/` page with a “Команда / Золото / Серебро / Бронза / Всего” table and two filters.
- Obtain years from end dates of saved challenges in UTC, descending; add “За весь период”. The year list is shared across all types and loads when the page opens.
- Add “Все типы / Командные / Проектные” selection, updating standings when either filter changes without reloading the page.
- Add `GET /api/challenges/years`, returning unique years; obtain medals from existing `GET /api/medals`.
- Use local HTML/CSS/JavaScript without a frontend framework, npm build, or external CDN; the same FastAPI serves the page and resources, including Docker installations.
- Provide loading, no-data, and error states with retry; ensure keyboard and narrow-screen usability.

## Capabilities

### New Capabilities

- `medals-web-ui`: browser medal standings with year and challenge type selection.

### Modified Capabilities

- `rest-api`: a new read-only endpoint listing end years of saved challenges.

## Impact

New web resources inside the Python package and a small page HTTP router; `api/app.py`, `api/routers/challenges.py`, `queries.py`, API/query tests, and resource serving checks. Additions to startup and project structure documentation. Verification that resources are included in the wheel and Docker image is mandatory. Migrations, database schema, and existing API contracts do not change. No new runtime dependencies are required.
