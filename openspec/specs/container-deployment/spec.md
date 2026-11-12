# container-deployment Specification

## Purpose

Deploying the database and REST API with one Docker Compose command, without manually installing Python on the server, and loading collected data from a CSV file on startup.

## Requirements

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

### Requirement: Migrations on startup
On every startup, the application container SHALL first apply database migrations to the latest version, then perform the startup import, and only then start the API. If migrations fail, the application MUST NOT start, and the container MUST exit with an error.

#### Scenario: Empty database
- **WHEN** the application starts with a new empty database
- **THEN** the schema is created, and the API responds

#### Scenario: Schema already up to date
- **WHEN** the container restarts without new migrations
- **THEN** migrations change nothing, and data are preserved

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

### Requirement: Exports on the host
CSV exports created in the container SHALL appear on the host in the project's `dumps/` directory. A CSV file from the host's `dumps/` directory SHALL be available for import inside the container, both on startup and manually.

#### Scenario: Export from the container
- **WHEN** `docker compose exec app python -m olympic_boinc.csv_transfer export` is executed
- **THEN** the file appears in `dumps/` on the host

#### Scenario: Manual import into a running container
- **WHEN** a CSV is placed in `dumps/` and `docker compose exec app python -m olympic_boinc.csv_transfer import dumps/<file>.csv` is executed
- **THEN** new challenges from the file appear in the container database and are served by the API

### Requirement: Self-hosted APM stack profile
Docker Compose SHALL provide an `observability` profile with Elasticsearch, Kibana, and APM Server at compatible pinned versions. The command `docker compose --profile observability up -d` SHALL start the application, PostgreSQL, and the observability stack, automatically preparing the required APM integration assets. Regular `docker compose up -d` MUST remain functional without starting the stack. The application MUST NOT have a mandatory readiness dependency on observability services.

#### Scenario: Full startup
- **WHEN** startup with the `observability` profile is performed and APM settings are filled in
- **THEN** after the stack is ready, container application telemetry is indexed and visible in Kibana without manually installing the integration through the UI

#### Scenario: Startup without the profile
- **WHEN** regular `docker compose up -d` is executed
- **THEN** the existing db and app start, and observability services are not required

### Requirement: Access from local and container applications
One stack SHALL accept application events from the host through port 8200 and from the container through the service address `apm-server:8200`. Kibana SHALL be available on host port 5601. Published APM and Kibana ports SHALL bind to the host loopback by default; Elasticsearch SHALL be available inside the Compose network without publishing 9200 on the host. Settings examples SHALL show both receiver addresses and agent enablement.

#### Scenario: Local application
- **WHEN** the stack is running and the application starts through uv with APM URL `http://127.0.0.1:8200`
- **THEN** its requests are visible in Kibana under the configured local environment

#### Scenario: Application in Compose
- **WHEN** APM is enabled in `.docker-env` with URL `http://apm-server:8200`
- **THEN** app transactions reach the same stack regardless of `.env` settings

### Requirement: Telemetry persistence and repeatable setup
Elasticsearch data SHALL be stored in a separate named volume and survive regular `docker compose down`/`up`. Integration setup SHALL be repeatable, wait for service readiness with bounded timeouts, and explicitly report failures. Setup failure MUST NOT block startup of the main application.

#### Scenario: Repeated startup
- **WHEN** the stack is stopped without deleting volumes and started again
- **THEN** previously recorded APM events are available, and setup does not break the already installed integration

#### Scenario: Setup error
- **WHEN** integration installation fails
- **THEN** the error is visible in observability setup logs, and the API and web UI continue to work

### Requirement: Self-hosted stack authentication and authorization
The stack SHALL use standard Elasticsearch and Kibana authentication and authorization. Administrator and service user passwords and the Kibana encryption key MUST be set in `.docker-env` and must not enter Git or setup logs. Service accounts SHALL be prepared automatically and repeatably; APM Server SHALL write events using a separate user without superuser privileges.

#### Scenario: First startup with authentication and authorization
- **WHEN** the profile starts with passwords and the encryption key filled in
- **THEN** service accounts and the integration are prepared automatically, and logging in to Kibana requires credentials

#### Scenario: Missing settings
- **WHEN** required stack credentials are not filled in
- **THEN** setup fails with a clear error without printing secrets; the main application does not depend on successful setup completion
