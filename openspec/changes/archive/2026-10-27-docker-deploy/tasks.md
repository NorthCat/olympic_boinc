# Tasks

## 1. Image

- [x] 1.1 `.dockerignore`: `.env`, `.git`, `.idea`, `.venv`, `__pycache__`, `*.egg-info`, `.pytest_cache`, `tests/`, `openspec/`, `logs/`, `dumps/`, `*.csv`. Verification: the built image contains no `/app/.env` or `/app/tests` (`docker run --rm --entrypoint ls <image> -a /app`).
- [x] 1.2 `docker/entrypoint.sh`: `set -e`, `alembic upgrade head`, import `$IMPORT_FILE` through `python -m olympic_boinc.csv_transfer import` if the file exists, otherwise a skip message; `exec uvicorn olympic_boinc.api.app:create_app --factory --host 0.0.0.0 --port 8000`. Without Xvfb. Verification: `sh -n docker/entrypoint.sh`, file is executable.
- [x] 1.3 `Dockerfile`: `python:3.13-slim` without apt packages, user with UID from `ARG UID=1000`, `WORKDIR /app`, copying `pyproject.toml`, `src/`, `alembic.ini`, `migrations/`, `pip install --no-cache-dir .`, `dumps` directory owned by `app`, entrypoint. Verification: `docker compose build app` passes; `python -c "import olympic_boinc"` works in the container, `chromium` and `Xvfb` are absent; the image is noticeably smaller than the previous 1.67 GB.

## 2. Compose

- [x] 2.1 `app` service in `docker-compose.yml`: `build: .`, `env_file: .env`, `environment` (database URL on `db:5432` from `POSTGRES_*`, `OLYMPIC_SCHEDULER_ENABLED: "false"`, `IMPORT_FILE: ${IMPORT_FILE:-dumps/import.csv}`), port `${APP_PORT:-8000}:8000`, `depends_on` db healthy, `restart: unless-stopped`, `init: true`, volume `./dumps:/app/dumps`, healthcheck on `/health`. Without browser variables, `shm_size`, or a `logs` volume. Verification: `docker compose config` has no errors; `app` has a database URL on `db:5432` and `OLYMPIC_SCHEDULER_ENABLED=false` with `localhost` and `true` values in `.env`.
- [x] 2.2 `dumps/` directory in the repository: `dumps/.gitkeep`, `.gitignore` rules `dumps/*` and `!dumps/.gitkeep`; `logs/` is again ignored entirely, `logs/.gitkeep` removed. Verification: `git check-ignore logs/sync.log dumps/x.csv` matches, `git status` shows only `dumps/.gitkeep`.

## 3. Documentation

- [x] 3.1 `README.md`, “Running in Docker” section: first startup, `APP_PORT`, `--build-arg UID`, password character restriction; startup import from `dumps/import.csv` and `IMPORT_FILE`, handling file errors (restart loop, `docker compose logs app`); manual export/import through `docker compose exec`; synchronization outside the container (why absent in the container, host synchronization to the database on port 5433, CSV transfer, advice to block external access to port 5433); updating (`docker compose build --pull`). `.env.example`: password without special characters, `APP_PORT`, `IMPORT_FILE`. `../../../../AGENTS.md`: Docker commands and files. Verification: section commands executed during verification (4.x).

## 4. Docker verification (requires Docker access)

- [x] 4.1 Start from scratch with project `-p olympic_check` without `dumps/import.csv`. Verification: container healthy, `/health` → 200; log shows applied migrations and an import skip message; repeated `restart` completes without migration errors.
- [x] 4.2 Startup import: export the local database to `dumps/import.csv`, `restart app`, then `restart` again, then manually export from the container. Verification: first startup log contains `added 22, skipped 0`, second contains `added 0, skipped 22`; `/api/medals` returns data; the export file appears in `dumps/` on the host and matches `import.csv` byte for byte.
- [x] 4.3 File error: `dumps/import.csv` with place 4 in one row. Verification: the container exits with a nonzero code, the API does not start, the log contains the line number and reason, and the database challenge count is unchanged. After removing the file, the container becomes healthy again.
- [x] 4.4 Synchronization does not run in the container: with `.env` containing `OLYMPIC_SCHEDULER_ENABLED=true` and `OLYMPIC_SYNC_ON_STARTUP=true`. Verification: no `Scheduler started` or `GET https://www.boincstats.com` in the log, no processes in the container except init and uvicorn.
- [x] 4.5 Synchronization from the host to the container database (without contacting the site): `csv_transfer import` from the host with `OLYMPIC_DATABASE_URL` on `localhost:5433`. Verification: the container API serves the imported challenge.
- [x] 4.6 Stop: `docker compose stop app`. Verification: the container stops before the timeout (10 s, without SIGKILL), and logs show graceful uvicorn shutdown.
- [x] 4.7 Remove the verification project (`docker compose -p olympic_check down -v`, verification files from `dumps/`), run `pytest`. Verification: verification volumes deleted, all tests pass.
