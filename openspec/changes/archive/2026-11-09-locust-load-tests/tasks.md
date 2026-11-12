# Tasks

## 1. Dependencies and structure

- [x] 1.1 Add optional extra `load` with a Python 3.13 compatible Locust version; verify `pip install -e '.[load]'` in the venv and `locust --version`.
- [x] 1.2 Create `load_tests/locustfile.py`, ignore `load_tests/reports/`; verify scenario discovery with `locust -f load_tests/locustfile.py --list` and exclusion of a probe report through `git check-ignore`.

## 2. Scenarios and correctness checks

- [x] 2.1 Implement user preparation through the challenge list, obtaining IDs, dates, and total, and stopping with diagnostics for empty or invalid data; verify on responses with nonsequential IDs, an empty list, and error 503.
- [x] 2.2 Implement the mixed profile with weights and delays from design, standings filter variants, list pagination, and card and health requests; verify each task and variant is called with correct parameters and only GET to the specified API.
- [x] 2.3 Add timeout, status and minimal JSON structure validation, matching IDs and `status=ok`, aggregate statistics names, and a nonzero exit code on failures; verify on controlled HTTP responses 500, HTML with 200, incorrect ID, and an empty initial sample, including the headless process exit code.

## 3. Execution instructions

- [x] 3.1 Write `load_tests/README.md`: installation, migrations and CSV import into a dedicated database, API startup with the scheduler disabled, interactive mode, smoke with 1 user / 30 seconds and a main headless example with 20 users / spawning 2 per second / 5 minutes with CSV and HTML; check commands against project paths and settings and add a link from the root README.
- [x] 3.2 Describe the profile, first-200-challenge sample, ramp-up, statistics, and recording environment and data volume; verify that instructions distinguish correctness errors from performance assessment without a defined SLA and contain no secrets.

## 4. Full run verification

- [x] 4.1 On a populated database, perform the documented smoke against a separately running API, then a run long enough for all variants; verify no failures, all scenarios present, CSV/HTML creation, and grouping of different IDs; record the command and environment parameters with a brief result.
- [x] 4.2 Perform a headless run against an empty database and an unavailable server; confirm clear diagnostics, a nonzero exit code, and no successful partial profile. Verify regular pytest does not collect load tests.
