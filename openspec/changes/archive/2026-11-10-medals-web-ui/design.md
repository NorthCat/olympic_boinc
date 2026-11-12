# Design

## Context

See `proposal.md` and delta specifications. `GET /api/medals` already returns aggregates in Olympic order and accepts `challenge_type=all|team|project`, `from`, and `to`. In `queries.get_medal_table`, dates are compared with UTC day boundaries. `/api/challenges` has pagination, so fetching all challenges from it solely for a year list is impractical. There is currently no static page.

The application is built by Hatchling from `src/olympic_boinc`; Docker installs the wheel in `/app/.venv` and removes `src`. Web resources must therefore be included in the package and located relative to the installed module. API/query tests already have an isolated PostgreSQL database, factories, and data at the 2025/2026 boundary. The OpenAPI test checks an exact path list and will need updating.

## Goals / Non-Goals

**Goals:** a simple standings page with two filters, one source of medal calculations in the API, dynamic years, minimal maintenance, operation through the same server and Docker image.

**Non-Goals:** SPA framework, Node/npm pipeline, separate frontend service or hosting, authentication and authorization, team cards, charts, custom sorting/search, table pagination, arbitrary date ranges, filter persistence in URL/localStorage, and timer-based refresh. The agreed scope of this change is plan preparation; publishing and source changes are not performed at this stage.

## Decisions

### 1. HTML/CSS and vanilla JavaScript in the existing application

Place `index.html`, `styles.css`, `app.js` in a new `src/olympic_boinc/web/` package with a resource directory. Add a small `GET /` router with `FileResponse`, hidden from OpenAPI, and serve CSS/JS through `StaticFiles` at `/static/`. Resolve paths relative to `__file__`, rather than the working directory. Do not mount a catch-all `/`, to avoid intercepting the API and unknown routes.

HTML contains a ready skeleton, native `select` elements, a table, and a status area; JS loads with `defer` and builds rows from JSON through the DOM API and `textContent`. With JS disabled, show `noscript` explaining that loading standings requires JavaScript. All API URLs are relative; frontend and API share an origin, so no CORS configuration is needed.

For two requests and two lists, jQuery provides insufficient benefit; vanilla JS avoids an additional dependency and CDN. Server-side Jinja templates would add a dependency and a second way of building the table, so are unnecessary now. The decision aligns with standard [static file serving in FastAPI](https://fastapi.tiangolo.com/tutorial/static-files/).

### 2. A separate small year list query

Add `GET /api/challenges/years` with `response_model=list[int]` to the existing challenges router **before** `/{challenge_id}`. The query function executes one SQL query: unique years from `Challenge.end_at`, converted to UTC through PostgreSQL `timezone('UTC', ...)`, sorted descending; convert values to integers. Do not load ORM objects or placements. No new tables, migrations, settings, or cache are needed.

The response contains only data, for example `[2026, 2025, 2023]`; the UI adds “За весь период”. The list is shared across the entire database regardless of selected type. This preserves the selected year when switching types; a combination without medals shows an empty result. The year list updates on page opening and retry of a failed load, not on a timer. This is the interpretation of the original request explicitly accepted for the first version.

### 3. Standings requests

Label-to-parameter mapping:

| Selection | `/api/medals` request parameters |
|---|---|
| За весь период | `from` and `to` absent |
| Year Y | `from=Y-01-01&to=Y-12-31` |
| Все типы | `challenge_type=all` |
| Командные | `challenge_type=team` |
| Проектные | `challenge_type=project` |

Use `URLSearchParams`; do not construct dates through the browser's local time zone. The year is determined by challenge end, including challenges that started earlier. Aggregation and sorting are performed only by the server. The UI displays every response row without its own reordering; teams without medals are excluded by the server.

On the first visit, load the year list, then standings with selected defaults. On a year error, do not declare the list empty: show an error with initial-load retry, and keep the year filter unavailable until the list is obtained successfully. After initialization, a select change triggers only a standings request.

### 4. Request state and errors

Store selected values and a monotonically increasing identifier for the current request. On a filter change, cancel the previous request through `AbortController`; also check the identifier before updating the DOM, error, and loading indicator. Ignore canceled and stale responses, including their completion handlers.

When an update starts, clear previous rows and show “Загрузка…”. After initialization, the filters themselves remain available so the selection can change. Success shows the table or an empty-data message; a network, HTTP, or invalid JSON error shows a clear message and “Повторить”. Retry sends a request for current filters; if years have not loaded, it repeats initial loading. Do not display stack traces, SQL, or infrastructure details to visitors.

### 5. Visual design

A calm, light page: “Медальный зачёт” heading, brief explanation of end year in UTC, then filters and table. Width-limited content, system font, no external images or fonts. Gold, silver, and bronze are indicated by text headers with soft color accents; numbers align right and the team name left. The “Всего” column is secondary to medal columns. Do not add a separate place column, to avoid introducing rank rules for equal medal counts.

Example structure (sample data):

```text
Medal standings
Challenge end year, UTC

Year                    Challenge type
[ All time        ▾ ]  [ All types        ▾ ]

Team                     Gold   Silver  Bronze  Total
Alpha                        2        0       1      3
Bravo                        1        2       0      3
```

On phones, filters are arranged vertically, and the table scrolls within its own container. Accessibility uses `label`, `th scope=col`, visible `:focus-visible`, `aria-live`/`aria-busy`, and an error area. Long names are not truncated without a way to read them.

### 6. Verification and delivery

Query/API tests use existing infrastructure and factories: duplicate years, gaps in the range, empty database, more than one challenge page, adding a new year, UTC with a different session timezone, `/years` and `/{id}` routing, preserving medals filters and exact OpenAPI paths. Verify HTML/CSS/JS serving and 404 through an ASGI client, rather than substituting file existence checks.

Browser acceptance is mandatory: compare numeric results with the API, cycle through both types and all time/year, check delayed responses in reverse order, API error and retry, empty data, literal HTML in a name, keyboard, and 360 px width. This is a separate check: Python coverage does not measure JavaScript. No new runtime dependencies or JS build are introduced; for the first version, repeatable manual browser acceptance with recorded results is allowed, without adding permanent browser infrastructure to the gate.

Check wheel contents after `uv build --wheel`: all three resources must be in the artifact. In an image with `src` removed, check `/`, resources, years, medals, and health; adjust Hatchling packaging if necessary. Update README and AGENTS. Final verification is the existing `./quality-gate.sh` with the Python coverage threshold of 90%, plus browser acceptance; existing routes and scheduler do not change.

## Risks / Trade-offs

- [Year in the local timezone differs from the API] → extract the year in UTC in SQL and pass calendar boundaries as strings; test a boundary instant.
- [Resources work from checkout but are missing from the wheel] → test the installed artifact/Docker without src.
- [An old response overwrites a new one] → request cancellation and a current-request identifier; verify reverse response order in the browser.
- [HTML in team names] → output only through `textContent`; verify literal display of a test name.
- [A year exists only in another type] → do not rebuild the list; show a clear empty result; behavior is described in specs.
- [The number of teams grows] → initially use the entire existing API response; consider pagination as a separate change if a volume issue is confirmed.

## Migration Plan

Introduce the new endpoint and UI without database migrations, build the package/image, and run as usual. The home page becomes available at `/`; existing API URLs remain. Rollback is the previous package/image version; data do not change.
