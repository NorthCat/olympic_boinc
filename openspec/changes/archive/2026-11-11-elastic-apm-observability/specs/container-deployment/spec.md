# Spec Delta

## ADDED Requirements

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
