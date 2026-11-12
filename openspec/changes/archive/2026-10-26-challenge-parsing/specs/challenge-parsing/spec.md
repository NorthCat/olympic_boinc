# Spec Delta

## Purpose

Extracting information about completed challenges and the teams that took the first three places from BoincStats HTML pages. These data form the basis of the medal standings.

## ADDED Requirements

### Requirement: List of completed challenges
The system SHALL extract all challenges with Completed status from an overview page (of project or team challenges). The following are extracted for each challenge:
- challenge type (based on the page from which it was obtained);
- name;
- project (if specified);
- start and end date and time;
- absolute link to the challenge page. The same challenge SHALL always receive the same link: it identifies the challenge in storage.

Challenges with any other status MUST NOT be included in the result.

#### Scenario: Mixed statuses
- **WHEN** the overview page contains challenges with Completed, Running, and Upcoming statuses
- **THEN** the result contains only challenges with Completed status

#### Scenario: Project and team challenges
- **WHEN** the project challenge overview is parsed, followed by the team challenge overview
- **THEN** challenges from the first page have type `project`, and those from the second have type `team`

### Requirement: Dates in UTC
The system SHALL convert challenge start and end dates to UTC, taking into account the time zone in which BoincStats displays them. Dates are returned as specified on the page, without corrections: for some challenges, BoincStats shows the end before the start (including 1970-01-01).

#### Scenario: Challenge period
- **WHEN** the page specifies the challenge period
- **THEN** the start and end are returned as UTC datetimes

#### Scenario: End before start
- **WHEN** the challenge end date on the page is before the start date (for example, 1970-01-01 00:00)
- **THEN** dates are returned as shown on the page, the challenge is not skipped, and there is no parsing error

### Requirement: Challenge podium finishers
The system SHALL extract teams with places from 1 to 3 from the challenge page. The team name, place, and score (if specified) are extracted for each team. The place SHALL be taken from the place column on the page if present; otherwise, the place SHALL be calculated from scores: teams with equal scores receive the same place, and the next team receives a place that accounts for all teams above it (“1, 1, 3”). If multiple teams have the same place (a tie), all of them SHALL be included in the result. Teams with a place greater than 3 MUST NOT be included in the result.

#### Scenario: Regular challenge
- **WHEN** a completed challenge page with team results is parsed
- **THEN** the teams that took 1st, 2nd, and 3rd places are returned, with names and scores

#### Scenario: Tie
- **WHEN** two teams are listed in 1st place on the page and the next is in 3rd
- **THEN** three teams are returned: two with place 1 and one with place 3

#### Scenario: Place by score
- **WHEN** the page has no place column and the first two teams have the same score
- **THEN** both receive place 1, and the next team receives place 3

### Requirement: Challenge without results
The system SHALL recognize a completed challenge page with no team results and return an empty list of podium finishers for it. This is not an error.

#### Scenario: Results not displayed
- **WHEN** a Completed challenge page on which BoincStats does not display a team results table is parsed
- **THEN** an empty list of podium finishers is returned

### Requirement: Error on unexpected markup
The system MUST report a parsing error if the page structure lacks expected elements (a challenge table on the overview; an indication of results or their absence on the challenge page). It MUST NOT silently return an empty result in this case.

#### Scenario: Overview markup changed
- **WHEN** no challenge table is found on the overview page
- **THEN** parsing fails with an error specifying which element was not found

#### Scenario: Another page received instead of the challenge page
- **WHEN** another page is parsed instead of the challenge results page (for example, the home page that BoincStats returns for a nonexistent address)
- **THEN** parsing fails with an error rather than an empty list of podium finishers
