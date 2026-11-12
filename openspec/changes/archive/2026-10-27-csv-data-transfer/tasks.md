# Tasks

## 1. Shared persistence

- [x] 1.1 Rename `sync._save` to public `save_challenge`, update the call in `run_sync`. Verification: `pytest tests/test_sync.py` passes without test changes.

## 2. Export and import

- [x] 2.1 `csv_transfer.py`: column constant and `export_csv(session_factory, path)` — one query ordered by `end_at, url, place, display_name`, writing through `csv.writer` in UTF-8. Verification: tests `test_export_empty_db_writes_header_only` and `test_export_rows_in_stable_order` on data from `tests/factories.py` (UTC dates, empty `project_name`/`score`, no IDs).
- [x] 2.2 `parse_csv(path) -> list[tuple[ChallengeSummary, list[TeamPlacement]]]` with error accumulation (`CsvImportError` with a list of “line N: reason”): header, type, dates (without a time zone → UTC), place 1–3, scores, empty required fields, differing fields for one link, duplicate team. Verification: a parameterized test for each error type and a test that all file errors are collected in one report with line numbers.
- [x] 2.3 `import_csv(session_factory, path) -> (added, skipped)`: `parse_csv`, then `save_challenge` for all challenges in one transaction. Verification: tests for repeated import (all skipped the second time), partial overlap, association with an existing team, and atomicity (a file with an error does not change the database).
- [x] 2.4 Round-trip test: export → import into an empty database → export produce identical files, including a team name with a comma, quotation marks, and non-ASCII characters. Verification: test `test_round_trip`.

## 3. Command line

- [x] 3.1 `python -m olympic_boinc.csv_transfer export [FILE] | import FILE`: argparse, export without a path to `dumps/` (in `.gitignore`), settings from `get_settings()`, “added N, skipped M” output, errors to stderr and exit code 1. Verification: CLI test through asynchronous `run(argv)` (`main` with `asyncio.run` cannot be called from the pytest-asyncio event loop) for successful import, export without a path to `dumps/`, and a file with errors (code 1).

## 4. Documentation and verification

- [x] 4.1 `README.md` (“Export and import” section: CSV, column format, difference from a dump, advice on CSV UTF-8 in Excel) and `../../../../AGENTS.md` (architecture and commands). Verification: both commands and the format are described.
- [x] 4.2 Manual verification on the dev database: export, import into a temporary empty database, compare files, repeat import reports “added 0”. Verification: files match, temporary database deleted.
