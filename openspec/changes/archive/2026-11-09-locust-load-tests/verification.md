# Implementation verification

Date: 2026-11-09. Python 3.13.15, Locust 2.47.0. Linux x86_64
7.0.0-38-generic, VM with 2 CPUs (Intel Core Ultra 7 255HX), about 11.3 GiB RAM.
API and generator on the same machine, loopback HTTP, uvicorn with one worker.
Local PostgreSQL 18; database settings unchanged, SQLAlchemy uses
the standard pool (size=5, max_overflow=10) with pool_pre_ping=True.

A unique temporary database with migrations to head was created for verification.
Existing export_csv/import_csv copied 66 podium rows:
22 challenges, 15 teams. The initial sample covers all 22 challenges.
The scheduler is disabled. The source database was used only for export;
after verification, the temporary database was dropped in finally.

## Commands and results

- `pip install -e '.[load]'`, `locust --version`, `locust -f load_tests/locustfile.py --list` — successful; OlympicUser discovered.
- `git check-ignore load_tests/reports/probe.html` — report ignored.
- `python -m unittest discover -s load_tests -v` — 5 tests passed. Checked all 14 groups, filter and page parameters, nonsequential IDs, HTTP 500/503, HTML with 200, missing structure, incorrect ID, empty preparation, and subprocess exit codes.
- `pytest --collect-only -q` — 141 tests selected, 1 live deselected; load tests are not collected.
- `openspec validate locust-load-tests --strict` and `git diff --check` — successful.

Real HTTP runs used common parameters:

```bash
locust -f load_tests/locustfile.py --host http://127.0.0.1:<temporary-port> \
    --headless --only-summary --users <users> --spawn-rate <rate> \
    --run-time <duration> --csv load_tests/reports/<name> \
    --html load_tests/reports/<name>.html
```

| Run | Users / rate / duration | Result |
|---|---|---|
| empty, before import | 1 / 1 / 3s | 1 request, 1 failure, exit 1, user stopped |
| smoke | 1 / 1 / 30s | 17 requests, 0 failures, exit 0 |
| verification | 20 / 2 / 90s | 861 requests, 0 failures, exit 0, all 14 groups |
| unavailable, after stopping the API | 1 / 1 / 3s | 1 request, 1 failure, exit 1 |

CSV and HTML were created in ignored `load_tests/reports/`. Cards are aggregated
under `/api/challenges/{id}` and `/api/teams/{id}`. Main run: about 9.67 RPS.
This verifies the profile's operation on a small data set with 1–3 second delays,
rather than measuring the throughput limit or confirming an SLA.
