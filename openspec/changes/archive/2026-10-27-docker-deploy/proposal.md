# Proposal

## Why

Currently, `docker-compose.yml` contains only the database. The application is installed manually: a venv, system Chrome, Xvfb, and a systemd unit file are needed. Server deployment needs one ready-to-use method: `docker compose up -d` starts the database and REST API with data already collected.

We are not moving synchronization into the container. Verification showed that Chromium in the container does not pass the Cloudflare check on BoincStats: the checkbox is clicked, but the check is not accepted. Synchronization therefore runs where it passes — outside the container. Data reach the container in one of two ways:
- CSV import (`csv_transfer`), performed automatically by the container on startup;
- directly into the container database through its host port.

## What Changes

- Application image (`Dockerfile`): Python 3.13 and the `olympic_boinc` package, without a browser or virtual display.
- `app` service in `docker-compose.yml` alongside `db`:
  - starts after the database is ready;
  - on every startup, applies migrations, then imports a CSV file if present, and only then starts the API;
  - publishes the API on a host port (default 8000);
  - restarts on failure and is checked through `/health`.
- Import on startup:
  - default file is `dumps/import.csv`; the path is set through the Compose variable `IMPORT_FILE`;
  - if the file does not exist, import is skipped;
  - restarting with the same file creates no duplicates;
  - if the file contains an error, the container exits with an error, as on migration failure.
- The scheduler is always disabled in the container, regardless of `.env`.
- Synchronization outside the container: the local application writes directly to the container database (`localhost:5433`), or data are transferred through CSV.
- Settings:
  - the database connection is assembled from `POSTGRES_USER`/`POSTGRES_PASSWORD` and points to `db:5432`;
  - other `OLYMPIC_*` settings come from `.env`.
- CSV exports and import files reside in the project's `dumps/` directory, mounted in the container. Manual export and import: `docker compose exec app python -m olympic_boinc.csv_transfer ...`.
- The previous “database only in Docker, application local” option (`docker compose up -d db`) continues to work.

## Capabilities

### New Capabilities
- `container-deployment`: database and API startup through Docker Compose, migrations and CSV import on startup, synchronization outside the container, container settings, access to exports from the host.

### Modified Capabilities

## Impact

- New files: `Dockerfile`, `.dockerignore`, `docker/entrypoint.sh`, `dumps/.gitkeep`.
- `docker-compose.yml`: `app` service.
- Application code does not change.
- Documentation: `README.md` (Docker section, data import, synchronization outside the container), `../../../../AGENTS.md`, `.env.example`.
- Building and verification require Docker access: the `docker` group or `sudo`.
