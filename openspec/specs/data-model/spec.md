# data-model Specification

## Purpose

Storage of completed BoincStats challenges, teams, and their podium placements. These data form the basis of the medal standings. This specification also defines the rules for determining whether teams and challenges are the same.

## Requirements

### Requirement: Challenge storage
The system SHALL store the following for each challenge:
- challenge type (`project` — project challenge, `team` — team challenge);
- name;
- BOINC project name (if known);
- start and end date and time in UTC;
- link to the challenge page.

Only challenges for which podium finishers have been obtained are stored.

#### Scenario: Saving a challenge with results
- **WHEN** a completed challenge with podium finishers is saved
- **THEN** a record with all the listed fields and podium placements appears in storage

### Requirement: Challenge uniqueness
The system MUST identify a challenge by the link to its page. Saving a challenge with the same link again MUST NOT create a duplicate.

#### Scenario: Saving again
- **WHEN** a challenge with the same link is saved a second time
- **THEN** storage rejects the duplicate, leaving one record for this challenge

### Requirement: Team identity by name
The system SHALL treat all records with the same name as one team. The name is stored and compared exactly as shown by BoincStats, without normalization. The team name MUST be unique.

#### Scenario: One team in different challenges
- **WHEN** the team “SETI.Germany” places in a project challenge and a team challenge
- **THEN** both results belong to the same team “SETI.Germany”

#### Scenario: Different teams
- **WHEN** two team names differ by at least one character, including case and spaces
- **THEN** they are two different teams

### Requirement: Podium placements
The system SHALL store only results with a place from 1 to 3 for a challenge. Each result stores the team, place, and score (if available). Multiple teams MAY have the same place in one challenge (a tie). One team MUST NOT have more than one result in one challenge.

#### Scenario: Tie for second place
- **WHEN** two teams are listed in 2nd place on the challenge page
- **THEN** both are saved with place 2

#### Scenario: Place outside the top three
- **WHEN** a result with a place greater than 3 or less than 1 is saved
- **THEN** storage rejects the record
