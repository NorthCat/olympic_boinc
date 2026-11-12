# scheduled-sync Specification

## Purpose

Automatic daily updates of challenge data to keep medal standings current without operator involvement.

## Requirements

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

### Requirement: Run log file
While the scheduler is running, the system SHALL write the following to a log file (default `logs/sync.log` relative to the application working directory, with a configurable path):
- scheduler start and stop;
- start and end of each synchronization run;
- address of every request to BoincStats, including retries;
- errors for individual challenges;
- run summary.

The file directory SHALL be created automatically. Log size MUST be limited: old records are displaced through rotation. Log records MUST also be sent to the regular application output. If the scheduler is disabled, the log file MUST NOT be created.

#### Scenario: Scheduled run
- **WHEN** synchronization starts on schedule and fetches several pages
- **THEN** the log file contains a line for the run start, a line for each requested URL, and a run summary line

#### Scenario: Run interrupted by blocking
- **WHEN** BoincStats displays a CAPTCHA during a run
- **THEN** the log file shows the URLs requested before it, the blocking error, and a summary with status `partial` or `failed`

#### Scenario: Directory does not exist
- **WHEN** the application starts with the scheduler enabled and the `logs` directory does not exist
- **THEN** the directory is created, and the log is written there

#### Scenario: Scheduler disabled
- **WHEN** the application starts with the scheduler disabled
- **THEN** the log file is not created

### Requirement: Synchronization on startup
The system SHALL allow synchronization to run immediately on application startup through a setting. This is disabled by default: synchronization runs only on schedule.

If the setting is enabled, the first run SHALL start on application startup, and subsequent runs follow the schedule as usual. The startup run SHALL follow the same rules as scheduled runs: it must not execute in parallel with another run, must release the browser after completion, and must be included in the run log. If the scheduler is disabled, synchronization on startup MUST NOT run.

#### Scenario: Setting enabled
- **WHEN** the application starts with the scheduler and startup run enabled
- **THEN** synchronization starts immediately without waiting for the schedule, and the next run occurs on schedule

#### Scenario: Setting disabled
- **WHEN** the application starts with the scheduler enabled and startup run disabled
- **THEN** synchronization does not start until the next scheduled time

#### Scenario: Scheduler disabled
- **WHEN** the startup run is enabled but the scheduler is disabled
- **THEN** synchronization runs neither on startup nor on schedule

#### Scenario: Scheduled time during a startup run
- **WHEN** the startup run is still running and the scheduled time arrives
- **THEN** the second run does not execute in parallel with the first
