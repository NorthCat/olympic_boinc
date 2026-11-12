# Spec Delta

## Purpose

Automatic daily updates of challenge data to keep medal standings current without operator involvement.

## ADDED Requirements

### Requirement: Periodic synchronization runs
While the application is running, the system SHALL automatically start synchronization according to the configured schedule. The schedule is specified as a cron expression in UTC, defaulting to once a day at 03:00 UTC.

#### Scenario: Scheduled run
- **WHEN** the application is running and the scheduled time arrives
- **THEN** synchronization starts, and its summary appears in the application log

#### Scenario: Custom schedule
- **WHEN** a different cron expression is configured
- **THEN** synchronization runs according to it

### Requirement: No overlapping runs
If the previous synchronization is still running when the next scheduled run is due, the new run MUST NOT start in parallel with it.

#### Scenario: Long synchronization
- **WHEN** scheduled synchronization is still running and the next run becomes due
- **THEN** the second run does not execute in parallel, and data are not corrupted

### Requirement: Resource cleanup after a run
The browser and other page-fetching resources SHALL be opened for the duration of one synchronization run and released afterward, regardless of the run outcome. The browser MUST NOT run between synchronization runs.

#### Scenario: Run ends with an error
- **WHEN** scheduled synchronization ends with an exception
- **THEN** the browser opened for this run is closed, and the next scheduled run executes as usual

### Requirement: Disabling the scheduler
The system SHALL allow automatic execution to be disabled through a setting. The rest of the application functionality continues to work.

#### Scenario: Scheduler disabled
- **WHEN** automatic execution is disabled in the configuration
- **THEN** the application starts and serves requests, but scheduled synchronization does not run

### Requirement: Graceful shutdown
When the application shuts down, the system SHALL stop the scheduler without starting new synchronization runs.

#### Scenario: Application shutdown
- **WHEN** the application shuts down
- **THEN** the scheduler stops, and no new runs start
