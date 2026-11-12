# Spec Delta

## Purpose

Deploying the database and REST API with one Docker Compose command, without manually installing Python on the server, and loading collected data from a CSV file on startup.

## ADDED Requirements

### Requirement: Startup with one command
The command `docker compose up -d` in the project root SHALL start the database and application. The application MUST start only after the database is ready to accept connections. The REST API SHALL be available on a host port, defaulting to 8000. Database data MUST persist across container restarts and recreation.

#### Scenario: First startup
- **WHEN** `docker compose up -d` is executed on a server with Docker in the project directory with a completed `.env`
- **THEN** after some time, `GET http://localhost:8000/health` returns 200 and `{"status": "ok"}`

#### Scenario: Recreating containers
- **WHEN** `docker compose down` is executed, followed by `docker compose up -d` again
- **THEN** previously saved challenges are still served by the API

### Requirement: Migrations on startup
On every startup, the application container SHALL first apply database migrations to the latest version, then perform the startup import, and only then start the API. If migrations fail, the application MUST NOT start, and the container MUST exit with an error.

#### Scenario: Empty database
- **WHEN** the application starts with a new empty database
- **THEN** the schema is created, and the API responds

#### Scenario: Schema already up to date
- **WHEN** the container restarts without new migrations
- **THEN** migrations change nothing, and data are preserved

### Requirement: Import on startup
After migrations and before starting the API, the container SHALL import a CSV file in the data transfer format. The file path is set through the Compose variable `IMPORT_FILE`, defaulting to `dumps/import.csv`. Import rules are the same as for manual import:
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

### Requirement: Synchronization outside the container
The application container MUST NOT start BoincStats synchronization or the browser, even if the scheduler is enabled in `.env`. Synchronization SHALL run outside the container. Its results reach the container database through CSV import or a connection from the host to the container database.

#### Scenario: Scheduler enabled in .env
- **WHEN** `.env` sets `OLYMPIC_SCHEDULER_ENABLED=true` and `OLYMPIC_SYNC_ON_STARTUP=true`
- **THEN** the container serves the API, and synchronization does not run or contact BoincStats

#### Scenario: Synchronization from the host to the container database
- **WHEN** the application outside the container runs with `OLYMPIC_DATABASE_URL` pointing to the container database port on the host
- **THEN** the challenges it saves are served by the container API

### Requirement: Connection and settings
The application database connection in Compose SHALL be assembled from the same credentials as the database service (`POSTGRES_USER`, `POSTGRES_PASSWORD` from `.env`). The `OLYMPIC_DATABASE_URL` value from `.env`, intended for local execution, MUST NOT affect the container. The `.env` file MUST NOT be included in the image.

#### Scenario: Local database address in .env
- **WHEN** `OLYMPIC_DATABASE_URL` in `.env` points to `localhost:5432`
- **THEN** the application in the container still connects to the Compose database service

### Requirement: Exports on the host
CSV exports created in the container SHALL appear on the host in the project's `dumps/` directory. A CSV file from the host's `dumps/` directory SHALL be available for import inside the container, both on startup and manually.

#### Scenario: Export from the container
- **WHEN** `docker compose exec app python -m olympic_boinc.csv_transfer export` is executed
- **THEN** the file appears in `dumps/` on the host

#### Scenario: Manual import into a running container
- **WHEN** a CSV is placed in `dumps/` and `docker compose exec app python -m olympic_boinc.csv_transfer import dumps/<file>.csv` is executed
- **THEN** new challenges from the file appear in the container database and are served by the API
