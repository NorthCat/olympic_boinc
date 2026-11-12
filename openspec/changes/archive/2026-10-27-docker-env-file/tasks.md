# Tasks

## 1. Settings files

- [x] 1.1 `.docker-env.example`: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `OLYMPIC_DATABASE_URL=postgresql+asyncpg://<user>:<password>@db:5432/olympic_boinc` with a comment about matching credentials and encoding special characters, commented-out `IMPORT_FILE`, explanation that synchronization is disabled in the container. `.docker-env` in `.gitignore` and `.dockerignore`. Verification: `git check-ignore .docker-env` matches, `.docker-env.example` is not ignored.
- [x] 1.2 `.env.example`: remove `POSTGRES_*`, `APP_PORT`, `IMPORT_FILE`, leave a reference to `.docker-env.example` for Docker. Verification: `grep -E "POSTGRES|APP_PORT|IMPORT_FILE" .env.example` finds only the reference.

## 2. Compose and entrypoint

- [x] 2.1 `docker-compose.yml`: `env_file: .docker-env` on `db` and `app`; remove `POSTGRES_*` substitutions from `db` (keep `POSTGRES_DB`); keep only `OLYMPIC_SCHEDULER_ENABLED: "false"` in `app`'s `environment`; port `${APP_PORT:-8000}:8000`. Verification: with a test `.docker-env`, `docker compose config` shows `app`'s URL and `IMPORT_FILE` from `.docker-env`, `OLYMPIC_SCHEDULER_ENABLED=false` despite `true` in `.docker-env`, and no values from `.env`; without `.docker-env`, `docker compose config` fails with the filename.
- [x] 2.2 `docker/entrypoint.sh`: `IMPORT_FILE="${IMPORT_FILE:-dumps/import.csv}"` before the file check. Verification: `sh -n`; starting without `IMPORT_FILE` logs “no import file dumps/import.csv”.

## 3. Documentation

- [x] 3.1 `README.md`: “Running in Docker” section — `.docker-env` instead of `.env`, explicit `OLYMPIC_DATABASE_URL`, encoding special characters instead of prohibiting them, `APP_PORT` through the shell, `IMPORT_FILE` in `.docker-env`, migration for existing installations; “Database” section (“database only in Docker” option) — credentials in `.docker-env`. `../../../../AGENTS.md`: Database and Docker lines. Verification: README no longer instructs setting Docker variables in `.env`.

## 4. Docker verification

- [x] 4.1 Project `-p olympic_check` with a test `.docker-env` (password containing special character `@`, encoded in the URL as `%40`) and your `.env` with `OLYMPIC_SCHEDULER_ENABLED=true` and a local URL. Verification: container healthy, `/health` → 200, no `Scheduler started` in the log, default import skipped.
- [x] 4.2 `IMPORT_FILE=dumps/check.csv` in `.docker-env` with one challenge, `docker compose up -d` (recreation). Verification: log contains `imported dumps/check.csv: added 1`, API serves the challenge.
- [x] 4.3 Without `.docker-env`: `docker compose config` and `up`. Verification: error with filename `.docker-env`, containers do not start.
- [x] 4.4 Cleanup: `docker compose -p olympic_check down -v --rmi local`, remove test `.docker-env` and `dumps/check.csv` (if you do not have your own `.docker-env`, do not touch someone else's), run `pytest`. Verification: no verification volumes or image remain, tests pass.
