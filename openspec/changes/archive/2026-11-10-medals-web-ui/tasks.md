# Tasks

## 1. Year list in REST API

- [x] 1.1 Add a query for unique challenge end years in UTC sorted descending; use query tests for an empty database, duplicates, both types, gaps in the range, and a year-boundary instant with a non-UTC session timezone.
- [x] 1.2 Add `GET /api/challenges/years` before the dynamic identifier route and include it in OpenAPI; verify `200`/`[]`, a JSON array of integers, updates after adding a year, completeness across multiple challenge pages, and existing `/{challenge_id}` behavior.
- [x] 1.3 Update the exact OpenAPI path check and ensure existing medal, filter, sorting, and tie API tests pass without changing the `/api/medals` contract.

## 2. Page and resources

- [x] 2.1 Add a web package with HTML skeleton, CSS, and JavaScript, route `/`, and `/static/` serving relative to the installed package; use ASGI tests to verify HTML, CSS/JS availability, 404 for a missing resource, and preservation of `/docs`, `/openapi.json`, `/health`, and the API.
- [x] 2.2 Style a Russian-language five-column table and two labeled filters, a light responsive page without external resources; verify in a browser on a wide screen and at 360 px, long names, textual medal labels, table semantics, visible focus, and keyboard control.

## 3. Dynamic behavior

- [x] 3.1 Implement initial loading of shared years and standings, “За весь период”/“Все типы” options, URL construction with UTC calendar boundaries; in the browser, verify no invented years and compare medals with the API for all types, a specific year, and all time.
- [x] 3.2 Update the table on either filter without reloading, preserving the other selection and server order; check a year existing only for another type, the correct empty result, and literal display of an HTML-like team name without executing markup.
- [x] 3.3 Add loading, empty-data, and error states with retry of the current request; reproduce year and medal errors and recovery in the browser, confirm preserved selection and no old rows under new filters.
- [x] 3.4 Protect DOM and statuses from stale/canceled requests; delay responses in the browser and return them in reverse order, checking table and state match the latest selection.

## 4. Delivery and acceptance

- [x] 4.1 Build the wheel through `uv build --wheel` and check for HTML/CSS/JS inside the artifact; adjust Hatchling packaging if necessary and confirm resources are available from the installed package without the source directory.
- [x] 4.2 Build the Docker image and check `/`, CSS/JS, `/api/challenges/years`, `/api/medals`, and `/health` in a separate Compose project; confirm operation after removing src, no separate frontend service, and the scheduler remaining disabled.
- [x] 4.3 Update README and AGENTS with the UI URL, years endpoint, and web resource location; verify uv commands are current and no new runtime dependencies/JS build exist.
- [x] 4.4 Run `./quality-gate.sh` with the current uv environment, save Ruff/mypy/pytest results and coverage of at least 90%; record browser acceptance separately for UI scenarios, check `git diff --check` and `openspec validate medals-web-ui --strict`.
