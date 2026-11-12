# Design

## Context

Currently, `docker-compose.yml` configures containers as follows:
- `db` uses `${POSTGRES_USER:?...}`/`${POSTGRES_PASSWORD:?...}` substitutions; Compose takes them automatically from the project's `.env`;
- `app` uses `env_file: .env` and `environment`, which overrides:
  - `OLYMPIC_DATABASE_URL`, assembled from `POSTGRES_*`;
  - `OLYMPIC_SCHEDULER_ENABLED=false`;
  - `IMPORT_FILE: ${IMPORT_FILE:-dumps/import.csv}`;
- port `${APP_PORT:-8000}:8000`.

`docker/entrypoint.sh` takes `$IMPORT_FILE` from the environment. The database healthcheck uses `$${POSTGRES_USER}`, meaning the environment variable inside the container.

## Goals / Non-Goals

**Goals:**
- Regular `docker compose ...` commands work without additional flags.

**Non-Goals:**
- Multiple environments (dev/prod) with different files.
- Secret storage through Docker secrets.
- Changing local execution: `.env` and `get_settings()` do not change.

## Decisions

- **`env_file: .docker-env` on both services, without substitutions from it.** Compose takes `${...}` substitutions in the compose file only from `.env`, shell variables, or a file passed through `--env-file`. Values from `env_file:` enter only the container environment. Everything containers need is therefore passed directly:
  - the `postgres` image reads `POSTGRES_USER`/`POSTGRES_PASSWORD` from the environment itself;
  - the application reads `OLYMPIC_*`;
  - the entrypoint reads `IMPORT_FILE`.

  The alternative is to assemble the URL from `POSTGRES_*` and require `--env-file .docker-env` on every command. Rejected because the flag is easy to forget, and compose would then silently use `.env`.
- **`OLYMPIC_DATABASE_URL` is written explicitly in `.docker-env`.** Credentials are duplicated as a result. However, the entire URL is visible, and the password special-character restriction is removed: if needed, the password in the URL is encoded (`%40` for `@`), while `POSTGRES_PASSWORD` remains as is. `.docker-env.example` contains a comment that values must match.
- **`.docker-env` is required** (short form `env_file: .docker-env`). If the file does not exist, compose immediately fails with “env file ... not found”. This replaces `${POSTGRES_USER:?...}` checks. The database healthcheck `$${POSTGRES_USER}` continues to work because it takes the variable from the container environment.
- **The default `IMPORT_FILE` value moves to the entrypoint:** `IMPORT_FILE="${IMPORT_FILE:-dumps/import.csv}"`. Compose no longer mentions `IMPORT_FILE`.
- **The scheduler remains disabled in `app`'s `environment`.** `environment` takes precedence over `env_file`, so `OLYMPIC_SCHEDULER_ENABLED=true` in `.docker-env` enables nothing. This preserves the “Synchronization outside the container” requirement.
- **The port remains a `${APP_PORT:-8000}` substitution.** The port number is a Compose parameter rather than part of the container environment, so it cannot be set through `env_file`. It can be changed through a shell variable (`APP_PORT=8080 docker compose up -d`). If `APP_PORT` accidentally appears in `.env`, Compose also picks it up, but documentation describes only the shell method.
- **`.env.example` is cleared of Docker variables** (`POSTGRES_*`, `APP_PORT`, `IMPORT_FILE`). They move to `.docker-env.example`.
- **`.docker-env.example` contains only what containers need:**
  - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `OLYMPIC_DATABASE_URL`;
  - commented-out `IMPORT_FILE`;
  - explanation that synchronization settings are unnecessary here.

## Risks / Trade-offs

- [`POSTGRES_PASSWORD` and the password in `OLYMPIC_DATABASE_URL` differ] → the application cannot connect and fails during migrations with an authentication error, visible in `docker compose logs app`. A template comment and README section warn about this.
- [After updating, an existing installation lacks `.docker-env`] → compose fails with a clear error. README describes migration: create `.docker-env` from `.docker-env.example` and move `POSTGRES_*` there from `.env`. Data in the `pgdata` volume are unaffected, but the password must match the one used when the volume was created.
- [The “database only in Docker” scenario now requires `.docker-env`] → expected: container database credentials reside there. The local application still takes its address from `.env`.

## Migration Plan

1. `cp .docker-env.example .docker-env`, move `POSTGRES_USER`/`POSTGRES_PASSWORD` from `.env`, and enter the same values in `OLYMPIC_DATABASE_URL`.
2. Remove `POSTGRES_*`, `APP_PORT`, `IMPORT_FILE` variables from `.env`. This is optional: containers no longer read them.
3. `docker compose up -d`.
