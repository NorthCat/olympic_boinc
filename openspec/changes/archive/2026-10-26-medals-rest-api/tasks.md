# Tasks

## 1. Queries and schemas

- [x] 1.1 `queries.py`: `get_medal_table(session, challenge_type, date_from, date_to)` using the SQL from design.md. Verification: a seeded database test — Olympic sorting, ties, `challenge_type` and period filters.
- [x] 1.2 `queries.py`: challenge list with podium finishers (pagination, `total`), one challenge, team card. Verification: seeded database tests.
- [x] 1.3 `api/schemas.py`: Pydantic response models (`MedalRow`, `ChallengeOut`, `PlacementOut`, `Page[T]`, `TeamOut`). Verification: `/openapi.json` is built without errors.

## 2. Routers

- [x] 2.1 `GET /api/medals` with validation of `challenge_type`, `from`, `to`. Verification: API tests for spec scenarios, including 422 for `challenge_type=foo`.
- [x] 2.2 `GET /api/challenges` and `GET /api/challenges/{id}`. Verification: API tests for pagination (page=2, size=10) and 404.
- [x] 2.3 `GET /api/teams/{id}`. Verification: API test for team medals and 404.
- [x] 2.4 `GET /health` (`SELECT 1`, 200/503). Verification: test 200; test 503 with an unavailable database (substituted session).
- [x] 2.5 Connect routers in `create_app`. Verification: all endpoints are present in `/openapi.json`.

## 3. Final verification and documentation

- [x] 3.1 End-to-end scenario: `docker compose up -d db`, `alembic upgrade head`, `uvicorn olympic_boinc.api.app:create_app --factory` with `OLYMPIC_SYNC_CRON="*/2 * * * *"`, wait for the synchronization summary in the log, `curl /api/medals`. Verification: standings sort correctly, and totals match `/api/challenges`.
- [x] 3.2 Update `../../../../AGENTS.md`: architecture (scraper → sync → db → api, scheduler), server startup, environment variables. Verification: instructions are reproducible in a clean environment.
