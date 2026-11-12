# Spec Delta

## ADDED Requirements

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
