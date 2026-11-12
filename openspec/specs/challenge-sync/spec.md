# challenge-sync Specification

## Purpose

Transferring completed BoincStats challenges and their podium finishers to local storage. The process is idempotent, minimizes requests to the source, and tolerates errors in individual challenges.

## Requirements

### Requirement: Coverage of both challenge types
Synchronization SHALL process both project and team challenges. Each BoincStats list displays all challenges on one page.

#### Scenario: Full traversal
- **WHEN** synchronization starts
- **THEN** overview pages for project and team challenges are fetched, one per type

### Requirement: Saving podium finishers of new challenges
For each Completed challenge not yet in storage (compared by link), synchronization SHALL fetch its page. If the page has results, it saves the challenge and its podium finishers, associating them with teams by name (exact match). If there are no results, the challenge MUST NOT be saved; it is considered skipped.

#### Scenario: New challenge with results
- **WHEN** a new Completed challenge with results appears in the list
- **THEN** after synchronization, storage contains this challenge and its podium finishers

#### Scenario: New challenge without results
- **WHEN** a Completed challenge whose page has no results appears in the list
- **THEN** the challenge is not saved and is counted as skipped in the run summary

### Requirement: Run size limit
In one run, synchronization SHALL fetch no more than the configured number of challenge pages (100 by default). Candidates are processed from newest to oldest (by end time). Candidates beyond the limit MUST NOT be fetched in this run; they remain for subsequent runs.

#### Scenario: More candidates than the limit
- **WHEN** there are 250 new Completed challenges and the limit is 100
- **THEN** pages for the 100 challenges with the latest end times are fetched, and the remaining 150 are counted as deferred in the summary and processed in subsequent runs

### Requirement: Idempotency and request minimization
Synchronization MUST NOT create duplicate challenges, teams, or results. It MUST NOT fetch pages of challenges already in storage again. Unsaved challenges (without results or with an error) are fetched again on each run.

#### Scenario: Repeated run
- **WHEN** synchronization runs a second time and nothing has changed on BoincStats
- **THEN** data in storage do not change; only overview pages and pages of unsaved challenges are fetched

#### Scenario: Results appear later
- **WHEN** results appear on the page of a challenge skipped because it had no results
- **THEN** the challenge and its podium finishers are saved on the next run

### Requirement: Tolerance of errors in individual challenges
An error fetching or parsing one challenge page MUST NOT interrupt processing of the others. The exception is blocking (a Cloudflare check or BoincStats CAPTCHA): in that case, the run SHALL stop to avoid further requests to the site that blocked it. Data for one challenge SHALL be saved atomically: either the entire challenge with all podium finishers, or nothing.

#### Scenario: Failure on one challenge
- **WHEN** the page of one of the new challenges cannot be parsed
- **THEN** the other challenges are saved, the run ends with status `partial`, and the error is logged

#### Scenario: Blocking during a run
- **WHEN** the site responds with a CAPTCHA or Cloudflare check while fetching a challenge page
- **THEN** no other pages are fetched in this run, challenges already saved remain, the run ends with status `partial`, and the reason is logged

#### Scenario: Challenge list unavailable
- **WHEN** an overview page cannot be fetched (for example, Cloudflare blocks it)
- **THEN** the run ends with status `failed`, the reason is logged, and data already saved do not change

### Requirement: Run summary in the log
Each synchronization run SHALL write a summary to the application log. Run history MUST NOT be persisted in storage. The summary contains:
- start and end time;
- status: `ok`, `partial`, or `failed`;
- number of added challenges;
- number of skipped challenges (without results or with an error);
- number of deferred challenges (not fetched because of the limit or an interruption);
- error descriptions.

#### Scenario: Successful run
- **WHEN** synchronization completes without errors
- **THEN** the log contains a record with status `ok` and the number of added challenges
