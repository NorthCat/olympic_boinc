# Design

## Context

`sync._save(session, summary, placements)` saves a challenge with podium finishers:
- inserts `Challenge` with `ON CONFLICT (url) DO NOTHING` and returns `False` if the challenge already exists;
- creates missing `Team` records;
- inserts `ChallengeResult`.

It takes `ChallengeSummary` and `TeamPlacement` (`score: int | None`) as input. In the database, `score` is `Numeric`; synchronization writes integers. The database connection is provided by `db.create_engine(settings.database_url)` and `db.create_session_factory`. Requirements are in `specs/data-transfer/spec.md`.

## Goals / Non-Goals

**Goals:**
- Import writes to the database using the same code as synchronization, so storage rules (link and team name uniqueness) apply consistently.

**Non-Goals:**
- Updating already saved challenges from a file.
- Deleting data absent from the file.
- REST export and import endpoints (the API remains read-only).
- The application Docker image is a separate change.

## Decisions

- **One flat file instead of one file per table.** A row contains everything about a podium placement, so the file can be read in a spreadsheet editor without matching IDs, and import does not depend on source database IDs and counters. The alternative — CSV per table through `COPY` — transfers internal IDs, conflicts with target database data, and repeats what `db_dump.py` already does.
- **Shared save function.** `_save` is renamed to `save_challenge` and remains in `sync.py`. Import calls it for each challenge in the file. A separate module solely for this function is unnecessary. Its merging of duplicate teams by best place does not affect import: import rejects duplicates during validation.
- **Validate first, then write.** The entire file is read into memory: there are thousands of challenges, which is not much. All rows are parsed; errors accumulate rather than stopping parsing at the first one. If there are no errors, rows are grouped by `url` into pairs of `ChallengeSummary` + a list of `TeamPlacement`.
- **One transaction for the entire import.** All `save_challenge` calls run in one session with `session.begin()`. Import therefore either completes entirely or leaves the database unchanged. The “skipped” counter is the number of calls returning `False`. This also works if concurrent synchronization has already saved the same challenge.
- **Field parsing.**
  - Dates are read through `datetime.fromisoformat`; UTC is assigned if no time zone is present. On export, dates are written through `isoformat()` in UTC.
  - Scores are `int`; on export, database `Decimal` is converted to `int`.
  - An empty `project_name` is read as `None`. Synchronization does not store an empty string in this field, so the two cannot be confused.
- **Export with one query:** `Challenge` ⋈ `ChallengeResult` ⋈ `Team` with `ORDER BY end_at, url, place, display_name`. Writing uses `csv.writer` with the standard `excel` dialect (RFC 4180, comma); the file is opened with `newline=""` and `encoding="utf-8"`.
- **CLI as a package module** `python -m olympic_boinc.csv_transfer export [FILE] | import FILE` (argparse, `asyncio.run`). The module is installed with the package, so unlike `scripts/`, commands will also be available in a future Docker image. A file path is required for import. Export without a path writes to `dumps/olympic_boinc_<UTC %Y%m%d_%H%M%S>.csv`. The directory is relative to the working directory, like `logs/` and `.env`, and is excluded from git. Validation errors are printed to stderr with exit code 1.
- **No confirmation.** Import only adds data; it neither deletes nor overwrites anything. This distinguishes it from `db_dump.py import`.

## Risks / Trade-offs

- [A file edited in Excel may have another encoding or use `;` as the delimiter] → header validation immediately rejects such a file with a clear error. README says to save as CSV UTF-8 with commas. We will not detect encoding and delimiter automatically.
- [An edit to an already saved challenge in the file is ignored during import] → this follows directly from the “unchanged” requirement. The report shows that the challenge was skipped. `db_dump.py import` exists for full data replacement.
- [Excel may convert dates to its own format] → such rows fail validation and appear in the report with line numbers.
