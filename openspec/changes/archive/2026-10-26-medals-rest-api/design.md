# Design

## Context

`create_app` with lifespan appears in `scheduled-sync`, models in `project-foundation`, and `run_sync` in `challenge-sync`. Requirements are in `specs/rest-api/spec.md`.

## Goals / Non-Goals

**Goals:**
- A read-only API, fast medal standings responses without caches.
- An OpenAPI schema suitable for generating a frontend client.

**Non-Goals:**
- Frontend, users and roles, caching, rate limiting.

## Decisions

- **Structure:**
  - `api/routers/*` — one module per resource;
  - `api/schemas.py` — Pydantic response models;
  - `queries.py` — SQL queries so they can be reused and tested separately from HTTP.
- **Medal standings — one aggregate query:**
  ```sql
  SELECT t.id, t.display_name,
         count(*) FILTER (WHERE r.place = 1) AS gold,
         count(*) FILTER (WHERE r.place = 2) AS silver,
         count(*) FILTER (WHERE r.place = 3) AS bronze,
         count(*) AS total
  FROM challenge_result r
  JOIN team t ON t.id = r.team_id
  JOIN challenge c ON c.id = r.challenge_id
  WHERE true [AND c.challenge_type = :challenge_type] [AND c.end_at BETWEEN :from AND :to]
  GROUP BY t.id
  ORDER BY gold DESC, silver DESC, bronze DESC, t.display_name
  ```
  Data volume is thousands of rows, so materialized views and a cache are unnecessary. The `(team_id, place)` index already exists.
- **Pagination:** `page`/`size` + `total` in the response. Offset pagination is sufficient at this volume.
- **The `from` parameter** is a Python reserved word, so `Query(alias="from")`. The `to` date is included through the end of the day (`< to + 1 day`).
- **Podium finishers in the challenge list** are fetched through `selectinload` to avoid N+1 queries.
- **No synchronization endpoints.** Only the scheduler (`scheduled-sync`) starts synchronization; its summary is in the application log.
- **CORS** is not enabled until a frontend exists. We will add the `cors_origins` setting with the frontend.

## Risks / Trade-offs

- [Team names with equal medal counts sort differently depending on database collation] → tests use the default collation; specify collation explicitly if needed (`COLLATE "C"`).
