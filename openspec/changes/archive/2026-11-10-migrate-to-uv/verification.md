# migrate-to-uv verification results

Date: 2026-11-10.

## Environments and versions

- uv 0.13.7; official image `ghcr.io/astral-sh/uv:0.13.7` is available.
- Old pyenv: Python 3.13.15, preserved unchanged.
- New external venv: Python 3.13.18; this version is recorded in `.python-version`.
- Comparison of all installed distributions: versions match. Only pip is absent from the new environment; no new third-party packages compared with the baseline.
- Temporary constraints removed before the final lock. `uv.lock` contains registry URLs and a relative editable project source; no secrets or absolute local paths.

Key versions: FastAPI 0.142.2, SQLAlchemy 2.1.1, Alembic 1.20.0, pytest 9.1.1, pytest-cov 7.1.0, Ruff 0.17.4, mypy 2.4.1, Locust 2.47.0.

## Quality gate

Before migration: `./quality-gate.sh` — code 0, 141 passed, 1 live test excluded, coverage 93.15%.

After migration:

```bash
UV_PROJECT_ENVIRONMENT=/home/mikhail/venvs/olympic_boinc_uv ./quality-gate.sh
UV_PROJECT_ENVIRONMENT=/home/mikhail/venvs/olympic_boinc_uv uv run --locked --extra load python -m unittest discover -s load_tests -v
```

Gate: code 0, Ruff without errors, mypy checked 40 files without errors, 141 passed, 1 live test excluded, coverage 93.15% with a 90% threshold. All 5 Locust tests passed.

Real negative checks were performed in an isolated temporary copy:

- Undefined name → Ruff F821, gate code 1; mypy and pytest also executed.
- Incorrect return type → mypy return-value, gate code 1; other checks executed.
- Failing test → gate code 1; Ruff and mypy executed.
- Added uncovered module → pytest tests pass, but coverage below 90% yields gate code 1.
- Mismatched manifest/lock → `uv sync --locked` refuses; the gate reports a preparation error and does not run checks in an unprepared environment.
- Clean sync and gate pass with a separate external environment and standard `.venv`; `uv lock --check` passes, and the lock remains unchanged after runs.

Working sources and the external working venv were not used to introduce test errors.

## Docker

`docker build -t olympic-boinc:uv-migration .` — successful.

Image check with networking disabled: application import works without `/app/src`, interpreter `/app/.venv/bin/python`, UID 1000, pytest/Ruff/mypy/Locust absent. The entrypoint does not install dependencies on startup.

In a separate Compose project with its own temporary PostgreSQL 18 volume and random local API port, verified:

- empty database migrations and health 200;
- skipping an absent CSV;
- settings from `.docker-env`, no `.env` effect on the application;
- disabled scheduler despite enabling settings in env_file;
- CSV import on startup, export to the host directory, and manual repeated import without duplication;
- repeated migration execution and data preservation after container recreation;
- refusal to start the API on a CSV error and a migration error.

Test containers, network, and temporary volume removed; existing dev containers and volumes unchanged.

## Completion

`bash -n quality-gate.sh`, `git diff --check`, and OpenSpec validation pass. Current instructions migrated to uv; pip/pyenv references preserved only in rollback descriptions. Archived artifacts and user changes in `.codex` were unchanged.

Manual step: select `/home/mikhail/venvs/olympic_boinc_uv/bin/python` in PyCharm; for uv project commands in the terminal/Run Configuration, set `UV_PROJECT_ENVIRONMENT=/home/mikhail/venvs/olympic_boinc_uv`. IDE and shell settings outside the repository were not automatically changed.
