# Bilingual web UI verification

Date: 2026-11-12.

## Automated checks

- `./quality-gate.sh` with the configured external uv environment: passed all six checks (Ruff, mypy, pytest, Bandit, pip-audit, Semgrep).
- Pytest: 251 passed, 1 live test deselected. Python line coverage 94.88%, threshold unchanged at 90%.
- Web delivery regression test now checks English default HTML and both language options from outside the repository working directory.
- `node --check src/olympic_boinc/web/static/app.js`, `openspec validate bilingual-web-ui --strict`, and `git diff --check`: passed.

## Packaged resources and browser acceptance

Built `/tmp/olympic-bilingual-dist/olympic_boinc-0.1.0-py3-none-any.whl` with `uv build --wheel`. Extracted and served its packaged HTML/CSS/JS through a temporary local HTTP server. Chromium 1243 was controlled through temporary Playwright; neither was added as a project dependency. API responses were intercepted locally, without contacting BoincStats or using application database data.

Ten acceptance groups passed:

1. First visit in a Russian-locale browser uses English, English document language/title, and both language choices.
2. English/Russian dictionary keys match; all marked text, metadata, and accessibility labels translate. Switching sends no API requests, preserves year/type and medal rows, and displays an HTML-like team name literally.
3. An explicit Russian choice survives reload.
4. Empty-result feedback and a zero team count translate immediately.
5. Medal-request errors, retry labels, and successful recovery retain selected filters.
6. Switching while a request is pending preserves the loading/busy state; completion uses the current language.
7. Year-list errors stay distinct from medal errors and recover through retry in the selected language.
8. Both languages fit a 360 px viewport without horizontal page overflow; language control has visible keyboard focus. Desktop/mobile screenshots were inspected.
9. Blocked localStorage and an unsupported saved value safely default to English; in-memory switching still works.
10. With cancellation deliberately bypassed, an older response arriving last cannot overwrite the latest filters, result, or language.

No JavaScript page errors. Temporary harness: `/tmp/olympic-bilingual-browser.py`; screenshots: `/tmp/olympic-bilingual-en-desktop.png`, `/tmp/olympic-bilingual-en-mobile.png`, `/tmp/olympic-bilingual-ru-mobile.png`. The owned HTTP server and browser were stopped after acceptance. Docker runtime was not rebuilt; asset delivery was verified from the wheel used by the existing Docker packaging flow.
