# medals-web-ui verification

Date: 2026-11-10.

## Automated checks

```bash
export UV_PROJECT_ENVIRONMENT=/home/mikhail/venvs/olympic_boinc_uv
./quality-gate.sh
```

Result: code 0; Ruff without errors; mypy without errors in 42 files; **152 passed**, 1 live test excluded; Python coverage **93.32%**, threshold 90% preserved.

Added 11 test cases: query/API for years (empty database, both types, sorting/uniqueness, gaps, new year, multiple pages, UTC boundaries with different session timezones) and HTTP resource serving (including from another working directory), 404, and API/docs availability. Regression tests for Olympic sorting, ties, filters, and health also pass. Existing fixtures with a separate database per run and transaction rollback were used.

`openspec validate medals-web-ui --strict` and `git diff --check` pass.

## Package and Docker

- `uv build --wheel --out-dir /tmp/olympic-web-dist` completed successfully; the wheel contains `index.html`, `styles.css`, `app.js` in `olympic_boinc/web/static/`.
- Image `olympic-boinc:web-ui` built, including after the final HTML edit.
- In a separate Compose project with PostgreSQL 18 and a random local port, checked `/`, `/static/styles.css`, `/static/app.js`, `/api/challenges/years`, `/api/medals`, `/health`, and `/docs`: HTTP 200, years `[2026, 2025, 2023]` match imported data.
- Resources are available from the installed package without `/app/src`, UID 1000; no separate frontend service. The scheduler is disabled even when env_file enables it and sync-on-startup.
- Test containers, network, and volume removed; the working database and existing volumes were unchanged.

## Browser acceptance

Verified in Chromium through temporary Playwright, which was not added to project dependencies. The page was served by the built Docker image, with test data imported through CSV. No browser JavaScript errors.

1. Cycled through all 12 combinations of “all time / 2026 / 2025 / 2023” and “all / team / project”. All rows, names, numbers, and order were checked against the real `/api/medals`.
2. Years have no duplicates, 2024 is not added; the list stays unchanged when switching type. For 2026 + project, no medals is shown.
3. Changed both filters with the keyboard, checked visible focus; activated error retry with Enter.
4. Intercepted requests to reproduce HTTP 503 for years and medals: clear separate messages, retry, preservation of the selected year, recovery after removing the error; old rows are cleared.
5. Empty year and medal arrays yield only “За весь период” and an empty-data message.
6. An HTML-like long name displays as literal text; no `img` appears in the DOM and the handler does not execute. Zero medal counts checked.
7. Visually checked the table at 1440 px; at 360 px, checked both filters, long names, no horizontal page overflow, and scrolling only within the table container. Screenshots reviewed; fixed spacing in the mobile UTC explanation.
8. To test a race, request cancellation was intentionally disabled by intercepting fetch. An old response was delayed and returned after a new one; the table and status remained consistent with the latest selection.

Local acceptance materials: `/tmp/olympic-web-browser.log`, `/tmp/olympic-web-preview/desktop.png`, `/tmp/olympic-web-preview/mobile.png`, `/tmp/olympic-web-preview/mobile-long-name.png`. Acceptance scripts: `/tmp/olympic-web-browser.py` and `/tmp/olympic-web-docker-qa.py`. These are temporary materials, not runtime dependencies or part of Python coverage.

To repeat manual verification: open `/` with data for multiple years and types, compare the table with `/api/medals`, then repeat steps 1–8 through DevTools (including request interception/delay). The Python gate does not replace JS browser testing.
