# Spec Delta

## ADDED Requirements

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
