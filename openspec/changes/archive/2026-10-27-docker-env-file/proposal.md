# Proposal

## Why

Currently, `.env` configures both local execution and Docker Compose. Compose therefore has to override its values for the container (database address, scheduler), and container database credentials reside alongside local ones. A separate container file separates these two environments: `.env` remains only for execution outside Docker, and everything containers see is specified in one place independently of local values.

## What Changes

- New container settings file `.docker-env`. Both compose services (`db` and `app`) read variables from it rather than `.env`:
  - `POSTGRES_USER`, `POSTGRES_PASSWORD` — for the database;
  - `OLYMPIC_DATABASE_URL` with host `db` — for the application, explicitly set rather than assembled from `POSTGRES_*`;
  - `IMPORT_FILE` and other `OLYMPIC_*` settings — for the application.
- **BREAKING**:
  - `docker compose` no longer takes container settings from `.env`. Before startup, create `.docker-env` using `.docker-env.example`. Without it, compose fails with a missing-file error.
  - `POSTGRES_*`, `APP_PORT`, `IMPORT_FILE` variables in `.env` no longer apply to containers.
- The API host port remains 8000. It can be changed through the `APP_PORT` environment variable when starting compose.
- The container scheduler remains forcibly disabled: compose sets `OLYMPIC_SCHEDULER_ENABLED=false` over `.docker-env`.
- The default import path (`dumps/import.csv`) is set in the entrypoint rather than through compose substitution.
- The repository contains a `.docker-env.example` template. `.docker-env` itself is excluded from git and the image.
- The “database only in Docker” scenario (`docker compose up -d db` and a local application on port 5433) remains: the database takes credentials from `.docker-env`, and the local application takes the address from `.env`.

## Capabilities

### New Capabilities

### Modified Capabilities
- `container-deployment`: container settings are specified in `.docker-env` rather than `.env`; the application database address is explicit; requirements “Startup with one command”, “Import on startup”, “Synchronization outside the container”, and “Connection and settings” change.

## Impact

- `docker-compose.yml`: `env_file: .docker-env` on both services, `POSTGRES_*` and `IMPORT_FILE` substitutions removed.
- `docker/entrypoint.sh`: default `IMPORT_FILE` value.
- New `.docker-env.example`. `.gitignore` and `.dockerignore`: `.docker-env`.
- `.env.example`: remove Docker variables (`POSTGRES_*`, `APP_PORT`, `IMPORT_FILE`).
- Documentation: `README.md` (“Database” and “Running in Docker” sections), `../../../../AGENTS.md`.
- Application code does not change.
