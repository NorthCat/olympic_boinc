# Spec Delta

## Purpose

Observability of the Olympic BOINC backend through Elastic APM: duration and errors of HTTP requests and background synchronization when running locally and in Docker Compose.

## ADDED Requirements

### Requirement: Configurable APM enablement
The system SHALL allow APM to be enabled and disabled through application settings with the `OLYMPIC_` prefix. APM SHALL be disabled by default. Settings SHALL include the receiver address, service name, environment, optional secret token, and proportion of sampled transactions from 0 to 1. Local execution SHALL read `.env`, and container execution, `.docker-env`. When APM is disabled, the system MUST NOT create the agent, start its background threads, or send telemetry.

#### Scenario: Disabled by default
- **WHEN** the application starts without enabling APM
- **THEN** the web UI, API, and scheduler work as before, with no APM requests

#### Scenario: Different environments
- **WHEN** local and container instances are enabled with different environment values
- **THEN** events from each instance contain its configured environment and service name

#### Scenario: Invalid sampling
- **WHEN** the proportion of sampled transactions is set outside the range from 0 to 1
- **THEN** the configuration is rejected with a clear error without exposing secrets

### Requirement: HTTP transactions and errors
When APM is enabled, the system SHALL record transactions for HTTP requests to the web UI and REST API with duration, method, route template, and HTTP result. An unhandled exception SHALL generate an associated error event. Resource identifiers and query strings MUST NOT create a separate transaction name. `/health` and `/static/` SHALL be excluded from HTTP transactions. Sampling settings SHALL control detail according to agent behavior; the presence of individual sampled events is verified at sampling 1.

#### Scenario: Successful request
- **WHEN** `GET /api/medals` is performed with APM enabled and sampling 1
- **THEN** a transaction with route `GET /api/medals`, duration, and a successful HTTP result is sent to the receiver

#### Scenario: Same route with different IDs
- **WHEN** `/api/teams/1` and `/api/teams/2` are requested
- **THEN** both transactions have the same name based on the route template, without specific IDs

#### Scenario: Unhandled error
- **WHEN** an HTTP request handler raises an unhandled exception
- **THEN** APM receives an error associated with the unsuccessful transaction, and the client receives the application's existing response

#### Scenario: Excluded requests
- **WHEN** requests to `/health` and `/static/styles.css` are performed
- **THEN** no HTTP transactions are created for them, and application responses remain unchanged

### Requirement: Background synchronization transactions
When APM is enabled, each scheduler run that actually starts SHALL have a separate background transaction named `sync`, with duration and result `ok`, `partial`, or `failed`. The `partial`/`failed` statuses MUST be determined by the synchronization result, even if no exception propagates. The added, skipped, and deferred counters SHALL be sent as numeric context. An unexpected scheduler exception SHALL be recorded as an error and end the transaction with result `failed`. The transaction SHALL end correctly when the run is canceled, without mixing with concurrent HTTP requests.

#### Scenario: Partially successful run
- **WHEN** synchronization returns status `partial` after being blocked by the site
- **THEN** APM contains one `sync` transaction with result `partial`, without an incorrect `ok` result

#### Scenario: Run exception
- **WHEN** a scheduler run ends with an unexpected exception
- **THEN** APM contains an error event and a completed `sync` transaction with result `failed`; normal fetcher cleanup and the ability to run again are preserved

#### Scenario: Scheduler disabled
- **WHEN** the application runs in Docker with the scheduler forcibly disabled
- **THEN** HTTP transactions are collected, but background `sync` transactions are not created

### Requirement: SQL spans and query text inspection
When APM is enabled, application SQL queries within sampled HTTP transactions and background `sync` transactions SHALL create associated spans of type `db.postgresql.query` with operation type, duration, and outcome. Spans SHALL contain sanitized SQL text in `db.statement`, preserving structure, table and column names, and parameter placeholders. Queries outside an APM transaction and at sampling 0 MUST NOT create separate SQL spans. Concurrent transactions MUST NOT mix SQL spans, and an SQL error SHALL end the corresponding span with an unsuccessful outcome without changing application behavior.

#### Scenario: SQL within an HTTP request
- **WHEN** `GET /api/medals` is performed with APM enabled and sampling 1
- **THEN** SQL spans belong to its HTTP transaction and contain duration, outcome, and sanitized SQL text for viewing in span details

#### Scenario: Background synchronization SQL
- **WHEN** a database query runs within a sampled `sync` transaction
- **THEN** the SQL span is associated with that background transaction

#### Scenario: SQL error
- **WHEN** an SQL query fails
- **THEN** its span ends with a failure outcome, the original error is preserved, and subsequent spans do not become its children because of an unfinished context

#### Scenario: Concurrent requests
- **WHEN** several sampled HTTP requests execute SQL concurrently
- **THEN** each SQL span is associated only with its request's transaction

#### Scenario: SQL without a sampled transaction
- **WHEN** SQL executes outside an APM transaction, with APM disabled, or at sampling 0
- **THEN** no separate SQL spans are created, and the query executes as usual

### Requirement: SQL sanitization before sending
SQL sent to APM SHALL preserve query structure but MUST NOT contain bound parameter values, string or numeric literals, or comments. Literals SHALL be replaced with `?`; sanitization SHALL handle PostgreSQL escape strings, dollar quoting, and nested block comments, as well as unterminated literals and comments. Sanitized SQL SHALL be limited to 10000 characters after sanitization. The connection address MUST NOT be added to SQL spans. Tests SHALL verify the actual serialized events.

#### Scenario: Parameterized query
- **WHEN** a query with a placeholder and a secret parameter value is executed
- **THEN** `db.statement` contains SQL with the placeholder, but the payload does not contain the parameter value

#### Scenario: Literals and comments
- **WHEN** a query contains string or numeric literals and comments with test values
- **THEN** the SQL span contains query structure with `?` instead of literals and without comments, and the test values are absent from the payload

#### Scenario: Long SQL
- **WHEN** sanitized SQL is longer than 10000 characters
- **THEN** no more than 10000 characters of sanitized text are sent, without exposing part of an original literal

### Requirement: Independence from receiver availability
APM Server unavailability, an authentication or authorization error, or a telemetry delivery error MUST NOT prevent application startup, change API responses, affect persistence of synchronization results, or cause `/health` to fail when the database is available. Delivery SHALL occur outside the request's critical path with bounded queue size, network wait, and shutdown wait. After the receiver recovers, new events SHALL be sent; delivery of all events from the period of unavailability is not guaranteed.

#### Scenario: Receiver unavailable
- **WHEN** the application enables APM but APM Server is not running
- **THEN** the application starts, the API responds, `/health` returns 200 when the database is available, and the delivery failure is visible in agent diagnostics

#### Scenario: Recovery
- **WHEN** the receiver becomes available after a failure
- **THEN** new HTTP transactions start arriving without changes to application data

### Requirement: Limiting collected data
Request bodies, Authorization/Cookie values, the APM secret token, and database URLs with credentials MUST NOT be sent to APM. Stack frame local variables SHALL be excluded from events. Errors SHALL retain diagnostic type and stack without secret values. Settings and tests SHALL confirm the absence of these data from the outgoing payload; the APM token is allowed only as a transport credential.

#### Scenario: Request with secrets
- **WHEN** a request contains a body, Authorization, and Cookie with test secret values
- **THEN** the telemetry payload does not contain these values or the request body

#### Scenario: Error with configuration in a local variable
- **WHEN** an exception occurs in a function with local database connection settings
- **THEN** the error event does not contain local variables with a DSN or APM secret token

### Requirement: Agent lifecycle
When APM is enabled, the application SHALL manage the agent for its lifecycle, with a bounded delivery completion time on shutdown. Repeated application creation in tests MUST NOT duplicate transactions, handlers, or background threads of closed instances. Existing application logs SHALL be preserved.

#### Scenario: Application shutdown
- **WHEN** the application lifespan ends
- **THEN** its agent closes without blocking shutdown indefinitely

#### Scenario: Repeated instances
- **WHEN** two applications with APM are created and closed sequentially in one process
- **THEN** a request to each instance creates exactly one transaction, and the closed instance does not leave a running transport
