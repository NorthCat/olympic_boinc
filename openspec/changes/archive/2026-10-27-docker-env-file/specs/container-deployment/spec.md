# Spec Delta

## MODIFIED Requirements

### Requirement: Startup with one command
The command `docker compose up -d` in the project root SHALL start the database and application. The application MUST start only after the database is ready to accept connections. The REST API SHALL be available on a host port, defaulting to 8000. Database data MUST persist across container restarts and recreation.

#### Scenario: First startup
- **WHEN** `docker compose up -d` is executed on a server with Docker in the project directory with a completed `.docker-env`
- **THEN** after some time, `GET http://localhost:8000/health` returns 200 and `{"status": "ok"}`

#### Scenario: Recreating containers
- **WHEN** `docker compose down` is executed, followed by `docker compose up -d` again
- **THEN** previously saved challenges are still served by the API

#### Scenario: Missing settings file
- **WHEN** `docker compose up -d` is executed in a directory without `.docker-env`
- **THEN** compose exits with an error naming the missing file, and containers do not start

### Requirement: Import on startup
After migrations and before starting the API, the container SHALL import a CSV file in the data transfer format. The file path is set by the `IMPORT_FILE` variable in `.docker-env`, defaulting to `dumps/import.csv`. Import rules are the same as for manual import:
- only challenges not yet present are added;
- the entire file is validated first.

If the file does not exist, import SHALL be skipped with a log message, and this MUST NOT be considered an error. If the file contains errors, the API MUST NOT start and the container MUST exit with an error; file errors SHALL be printed to the container log. The import summary (added, skipped) SHALL be printed to the container log.

#### Scenario: File does not exist
- **WHEN** the container starts and `dumps/import.csv` does not exist
- **THEN** the log contains a message that import was skipped, and the API starts

#### Scenario: First import
- **WHEN** `dumps/import.csv` contains an export with 22 challenges and the database is empty
- **THEN** the log contains “added 22, skipped 0”, and the API serves these challenges

#### Scenario: Restart with the same file
- **WHEN** the container restarts and the file has not changed
- **THEN** nothing is added, the log contains “added 0, skipped 22”, and there are no duplicates

#### Scenario: Error in the file
- **WHEN** the import file contains a row with place 4
- **THEN** the container exits with an error, the API does not start, the log specifies the line and reason, and the database does not change

#### Scenario: Another import file
- **WHEN** `.docker-env` sets `IMPORT_FILE=dumps/2026-10.csv` and that file exists in `dumps/`
- **THEN** that file is imported on startup

### Requirement: Synchronization outside the container
The application container MUST NOT start BoincStats synchronization or the browser, even if the scheduler is enabled in `.docker-env`. Synchronization SHALL run outside the container. Its results reach the container database through CSV import or a connection from the host to the container database.

#### Scenario: Scheduler enabled in .env
- **WHEN** `.env` sets `OLYMPIC_SCHEDULER_ENABLED=true` and `OLYMPIC_SYNC_ON_STARTUP=true`
- **THEN** this does not affect the container: it serves the API, and synchronization does not run

#### Scenario: Scheduler enabled in .docker-env
- **WHEN** `.docker-env` sets `OLYMPIC_SCHEDULER_ENABLED=true` and `OLYMPIC_SYNC_ON_STARTUP=true`
- **THEN** the container serves the API, and synchronization does not run or contact BoincStats

#### Scenario: Synchronization from the host to the container database
- **WHEN** the application outside the container runs with `OLYMPIC_DATABASE_URL` pointing to the container database port on the host
- **THEN** the challenges it saves are served by the container API

### Requirement: Connection and settings
Container settings SHALL be specified in the `.docker-env` file in the project root, separate from `.env`. Both services take variables from it:
- database — `POSTGRES_USER` and `POSTGRES_PASSWORD`;
- application — `OLYMPIC_DATABASE_URL` with the database service host, `IMPORT_FILE`, and other `OLYMPIC_*` settings.

Values from `.env` MUST NOT affect containers. The `.env` and `.docker-env` files MUST NOT be included in the image or git; the repository SHALL contain a `.docker-env.example` template.

#### Scenario: Local database address in .env
- **WHEN** `OLYMPIC_DATABASE_URL` in `.env` points to `localhost:5432` and in `.docker-env` to `db:5432`
- **THEN** the container application connects to the Compose database service, and a local run connects to the local database

#### Scenario: Setting only in .env
- **WHEN** `IMPORT_FILE` is set only in `.env`
- **THEN** the container does not see it and imports the default file `dumps/import.csv`
