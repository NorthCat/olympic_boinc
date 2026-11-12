# Design

## Context

- `docker-compose.yml` contains only the `db` service: `postgres:18`, credentials from `POSTGRES_USER`/`POSTGRES_PASSWORD` in `.env`, host port 5433, `pgdata` volume, healthcheck through `pg_isready`.
- The application starts with `uvicorn olympic_boinc.api.app:create_app --factory`.
- Settings are `OLYMPIC_*` variables (pydantic-settings) plus `.env` from the working directory.
- `OLYMPIC_SCHEDULER_ENABLED=false` fully disables the scheduler, along with the synchronization log and browser.
- `python -m olympic_boinc.csv_transfer import FILE` imports CSV idempotently. For file errors, the command returns code 1 and prints them to stderr.
- Alembic migrations need `alembic.ini` and `migrations/`; they take the database URL from settings.
- `/health` responds with 200 if the database is available.
- Build verification showed that Debian Chromium in a container under Xvfb does not pass the Cloudflare check on BoincStats: the checkbox is clicked, but the check is not accepted. Synchronization therefore does not run in the container (see proposal.md).

## Goals / Non-Goals

**Goals:**
- Application code does not change: the container is another way to run it.
- Data reach the container without manual commands: place the file and start the container.

**Non-Goals:**
- Synchronization with BoincStats in the container.
- Publishing the image to a registry, CI, multi-architecture builds.
- Reverse proxy and HTTPS.
- A separate compose file for development: local development uses a venv, and `docker compose up -d db` remains.
- Deleting or moving the file after import: the file remains in place, and repeated import is safe.

## Decisions

- **`python:3.13-slim` image without apt packages.** The browser and Xvfb are unnecessary because there is no synchronization in the container. The image is about 1 GB smaller. Package dependencies (nodriver, opencv) are installed with it: they are needed when importing modules and are tiny compared with the browser. Moving them into a separate dependency group solely for the image is not worthwhile.
- **The package is installed with regular `pip install .`, without editable mode.** `pyproject.toml`, `src/`, `alembic.ini`, and `migrations/` are copied into the image. The working directory is `/app`, so `dumps/` resolves to `/app/dumps`.
- **`docker/entrypoint.sh` (`set -e`):**
  1. `alembic upgrade head`;
  2. if `$IMPORT_FILE` exists, `python -m olympic_boinc.csv_transfer import "$IMPORT_FILE"`; otherwise, a “no import file ..., skipping” line;
  3. `exec uvicorn ... --host 0.0.0.0 --port 8000`.

  A nonzero migration or import exit code ends the container before the API starts. Import runs as a separate process through the existing CLI: no code needs to be added to it, and errors use the same format as manual import. `exec` makes uvicorn the main process, so `docker stop` reaches it. Compose sets `init: true`.
- **The `IMPORT_FILE` path** is set in compose: `IMPORT_FILE: ${IMPORT_FILE:-dumps/import.csv}`. This is a Compose variable without the `OLYMPIC_` prefix, like `APP_PORT`, because the application does not read it. The path resolves relative to `/app`.
- **A file error crashes the container rather than starting without import.** Otherwise the error is easy to miss: the API works, but there are no data. With `restart: unless-stopped`, the container keeps restarting. This is visible in `docker compose ps` (Restarting) and `docker compose logs app`. Fix or remove the file to resolve it.
- **The scheduler is disabled in compose:** `OLYMPIC_SCHEDULER_ENABLED: "false"` in `environment`, which overrides `env_file`. Thus the same `.env` with `true` for local execution will not start site requests from the container. Browser variables are no longer needed in compose.
- **Non-root user.** UID is set through the build argument `UID` (default 1000), so files in the mounted `dumps/` belong to the host user.
- **`dumps/` exists in the repository** (`.gitkeep`, rules `dumps/*` and `!dumps/.gitkeep`). If the directory does not exist, Docker creates it as root when mounting, and the container user cannot write to it. `logs/` is no longer mounted in the container, so `.gitignore` again ignores it entirely, without `.gitkeep`.
- **Settings in compose:**
  - `env_file: .env`;
  - `environment`:
    - `OLYMPIC_DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/olympic_boinc`;
    - `OLYMPIC_SCHEDULER_ENABLED=false`;
    - `IMPORT_FILE`.

  `.env` is excluded through `.dockerignore`.
- **`app` service:**
  - port `${APP_PORT:-8000}:8000`;
  - `depends_on: db: condition: service_healthy`;
  - `restart: unless-stopped`;
  - `init: true`;
  - volume `./dumps:/app/dumps`;
  - healthcheck: `python -c` with `urllib` to `/health`, `start_period` for migrations and import;
  - build `build: .`.
- **Synchronization outside the container.** Database port 5433 is published on the host. The local application running with `OLYMPIC_DATABASE_URL=...@localhost:5433/olympic_boinc` synchronizes directly into the container database. The second option is CSV: local export, then place the file in `dumps/import.csv` and restart the container or import manually.

## Risks / Trade-offs

- [An error in `import.csv` causes a container restart loop] → a deliberate choice. README describes how to see it (`docker compose ps`, `docker compose logs app`) and fix it.
- [A large file is parsed again on every startup] → parsing thousands of rows takes fractions of a second, and nothing is written again. If startup slows down, the file can be removed after a successful import.
- [A database password with special characters (`@`, `/`, `:`, `%`, `#`) breaks the assembled URL] → README and `.env.example` state that the password must not contain such characters.
- [Host user UID is not 1000] → `docker compose build --build-arg UID=$(id -u)`, described in README.
- [Database port 5433 is externally accessible on the server] → it is needed for synchronization from the host. README recommends closing it with a firewall or publishing only on `127.0.0.1` if synchronization runs on the same machine.
- [Data in the container update only when someone synchronizes or imports externally] → this follows from the decision not to synchronize in the container. README describes both methods.

## Migration Plan

1. On the server: clone the project, fill in `.env` (`POSTGRES_USER`, `POSTGRES_PASSWORD`), put the export in `dumps/import.csv`, run `docker compose up -d --build`.
2. New data:
   - either synchronize from the host directly into the container database (`OLYMPIC_DATABASE_URL` on port 5433);
   - or place a fresh export in `dumps/import.csv` and run `docker compose restart app`.

Rollback: `docker compose stop app` and run as before, through a venv or systemd. Data in the `pgdata` volume remain.
