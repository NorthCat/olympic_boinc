# data-transfer Specification

## Purpose

Transferring collected challenges and their podium finishers between databases through a text CSV file: exporting all results and importing them into another database without contacting BoincStats again.

## Requirements

### Requirement: CSV file format
The file SHALL use UTF-8 encoding, a comma delimiter, quoting according to RFC 4180, and a header row. One file row represents one podium placement. Columns in this order:
- `challenge_type` — `project` or `team`;
- `challenge_name` — challenge name;
- `project_name` — BOINC project name, empty if unknown;
- `start_at`, `end_at` — start and end in ISO 8601 format with a time zone (UTC on export);
- `url` — link to the challenge page;
- `team` — team name exactly as shown by BoincStats;
- `place` — place from 1 to 3;
- `score` — score, a nonnegative integer, empty if unknown.

Internal database identifiers MUST NOT be included in the file.

#### Scenario: Challenge with three podium finishers
- **WHEN** a challenge with three podium finishers is exported
- **THEN** the file contains three rows with identical challenge fields and different teams

#### Scenario: Team name with a comma and quotation marks
- **WHEN** a team name contains a comma or quotation marks
- **THEN** the name remains exactly the same after export and import

### Requirement: Export
The system SHALL export all saved challenges with their podium finishers to a CSV file. Rows MUST follow a defined order: by challenge end date, then by link, place, and team name, so that exporting the same data again produces the same file.

#### Scenario: Empty database
- **WHEN** a database without challenges is exported
- **THEN** the file contains only the header row

#### Scenario: Transfer to an empty database
- **WHEN** a file exported from one database is imported into an empty database and then exported from it
- **THEN** both files are identical

### Requirement: File validation before import
Before writing to the database, the system MUST validate the entire file. The following are errors:
- a missing or extra column in the header;
- an unknown challenge type, invalid date, place outside 1–3, invalid score, empty name, link, or team name;
- rows for one challenge (with the same link) that have differing challenge fields;
- the same team appearing twice in one challenge.

A date without a time zone SHALL be treated as a UTC date. On any error, the system MUST NOT change the database and SHALL report all errors found with file line numbers.

#### Scenario: Error in one row
- **WHEN** place is 4 on line 17 of a 30-line file
- **THEN** the database does not change, and the report specifies line 17 and the reason

#### Scenario: Inconsistent challenge fields
- **WHEN** two rows with the same link contain different end dates
- **THEN** the import is rejected with these rows identified

### Requirement: Merging with existing data
Import SHALL add only challenges whose links are not yet in the database. An existing challenge MUST be skipped entirely: its fields and podium finishers are neither compared nor changed. Teams SHALL be matched to existing teams by exact name, and missing teams are created. Import MUST NOT create duplicate challenges, teams, or results, including when the same file is imported again. All additions within one import MUST be performed atomically.

#### Scenario: Repeated import
- **WHEN** the same file is imported twice
- **THEN** the second import adds nothing and reports that all challenges were skipped

#### Scenario: Partially overlapping data
- **WHEN** the database contains 10 challenges and the file contains 15, of which 10 are the same
- **THEN** 5 new challenges are added and 10 are skipped

#### Scenario: Team already exists
- **WHEN** a team from the file already exists in the database with the same name
- **THEN** new results are associated with the existing team, and no new team is created

### Requirement: Command-line execution
Export and import SHALL be run from the command line with a file path. The path is required for import. Without a path, export SHALL save the file in the `dumps` directory relative to the working directory (creating the directory), with the export date and time in UTC in the name. The database connection is taken from application settings. Import SHALL print the number of added and skipped challenges. On error, the command MUST exit with a nonzero exit code.

#### Scenario: Successful import
- **WHEN** a valid file with 5 new and 2 already saved challenges is imported
- **THEN** the command reports “added 5, skipped 2” and exits with code 0

#### Scenario: Export without a path
- **WHEN** export runs without a file path and the `dumps` directory does not exist
- **THEN** the directory is created and the file `olympic_boinc_<date>_<time>.csv` is saved in it

#### Scenario: Invalid file
- **WHEN** a file with errors is imported
- **THEN** the command prints the errors and exits with a nonzero code
