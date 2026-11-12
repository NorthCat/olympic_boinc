# Spec Delta

## Purpose

Provide reproducible load on the Olympic BOINC REST API and obtain latency, throughput, and error statistics with concurrent clients.

## ADDED Requirements

### Requirement: Read operation coverage

The load test suite SHALL perform GET requests for medal standings, the challenge list, the challenge card, the team card, and the health check. The suite SHALL include unfiltered standings, `challenge_type` filters with `project` and `team` values, a valid `from`/`to` period, and a list with different pages and sizes within allowed limits. The suite SHALL contact only the specified API server, without following BoincStats links or modifying data.

#### Scenario: Mixed load
- **WHEN** a sufficiently long run is performed against a populated database
- **THEN** all listed scenarios are available, and statistics distinguish operations and filter and pagination variants separately

### Requirement: Using existing data

Tests SHALL obtain challenge and team IDs from API responses, without assumptions about ID sequences. If the database is empty or valid data cannot be obtained, the load test user SHALL stop with an explicit diagnostic; such a run MUST NOT be presented as a successful full test.

#### Scenario: Nonsequential IDs
- **WHEN** the database contains challenges and podium finishers with arbitrary positive IDs
- **THEN** card requests use the obtained IDs and expect a successful response

#### Scenario: Empty database
- **WHEN** the challenge list is empty
- **THEN** the test reports that the database needs to be populated and does not continue a partial profile as a successful full run

### Requirement: Response errors included in statistics

Tests SHALL count a network failure, an HTTP status other than 200, invalid JSON, and missing required response structure as errors. Checks SHALL verify that card IDs match the request and that `/health` has `status=ok`. Errors SHALL appear in statistics and cause a nonzero exit code for a headless run, including data preparation errors.

#### Scenario: Invalid successful response
- **WHEN** the server returns HTTP 200 with HTML or a card without the expected ID
- **THEN** the request is recorded as an error rather than a successful operation

#### Scenario: Data preparation error
- **WHEN** the initial list request receives HTTP 503
- **THEN** the run reports a preparation error and exits with a nonzero code

### Requirement: Configurable execution and reporting

The suite SHALL support interactive and headless execution with the server address, number of users, spawn rate, and duration specified by the operator. Headless execution SHALL allow saving CSV and HTML with request counts, error rate, RPS, and latency percentiles. Different IDs SHALL be aggregated under one route template.

#### Scenario: Reproducible run
- **WHEN** the operator runs the documented headless command with load parameters and report paths
- **THEN** the run is limited to the specified duration and saves reports in which cards with different IDs are grouped by route

### Requirement: Environment preparation instructions

Documentation SHALL describe installing the optional load dependency, running the application separately with the scheduler disabled, migrations and database population through the existing CSV import, a short check, and the main run. Documentation SHALL require recording data volume, load parameters, and application and PostgreSQL configuration for comparing results. Generated reports SHALL be excluded from Git.

#### Scenario: First run
- **WHEN** a developer follows the instructions with an available CSV and PostgreSQL
- **THEN** they can prepare the server and perform a short run without a browser or requests to BoincStats
