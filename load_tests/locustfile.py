"""Read-only HTTP workload. Run separately from the API (see README.md)."""

import logging
import random
from datetime import UTC, datetime
from itertools import cycle

from locust import HttpUser, between, events, task
from locust.exception import StopUser

logger = logging.getLogger(__name__)
BASE = {"id", "challenge_type", "name", "project_name", "start_at", "end_at", "url"}
MEDALS = {"gold", "silver", "bronze", "total"}


def fields(value, required):
    if not isinstance(value, dict) or not required <= value.keys():
        raise ValueError(f"Expected object with fields: {', '.join(sorted(required))}")


def rows(value, validate):
    if not isinstance(value, list):
        raise ValueError("Expected JSON array")

    for row in value:
        validate(row)


def challenge(value):
    fields(value, BASE | {"placements"})
    if type(value["id"]) is not int or value["id"] <= 0:
        raise ValueError("Expected positive challenge ID")

    rows(value["placements"], placement)


def placement(value):
    fields(value, {"team_id", "team_name", "place", "score"})
    if type(value["team_id"]) is not int or value["team_id"] <= 0:
        raise ValueError("Expected positive team ID")


def page(value):
    fields(value, {"items", "total", "page", "size"})
    if any(type(value[k]) is not int for k in ("total", "page", "size")):
        raise ValueError("Expected integer pagination")
    if value["total"] < 0 or value["page"] < 1 or not 1 <= value["size"] <= 200:
        raise ValueError("Invalid pagination")

    rows(value["items"], challenge)


def medal_table(value):
    rows(value, lambda row: fields(row, MEDALS | {"team_id", "team_name"}))


def team(value):
    fields(value, MEDALS | {"id", "name", "challenges"})
    rows(value["challenges"], lambda row: fields(row, BASE | {"place"}))


def health(value):
    fields(value, {"status"})
    if value["status"] != "ok":
        raise ValueError("Expected health status=ok")


@events.test_start.add_listener
def reset_run(environment, **kwargs):
    environment.load_preparation_failed = False


@events.quitting.add_listener
def fail_exit_code(environment, **kwargs):
    if (
        environment.stats.total.num_failures
        or environment.runner.exceptions
        or getattr(environment, "load_preparation_failed", False)
    ):
        environment.process_exit_code = 1


class OlympicUser(HttpUser):
    wait_time = between(1, 3)

    def get_checked(self, path, name, validate, params=None, expected_id=None):
        # No redirects: neither an API redirect nor a stored source URL may
        # send this generator to BoincStats or another host.
        with self.client.get(
            path, name=name, params=params, timeout=15, allow_redirects=False, catch_response=True
        ) as response:
            try:
                if response.status_code != 200:
                    raise ValueError(f"Expected HTTP 200, got {response.status_code}")

                value = response.json()
                validate(value)
                if expected_id is not None and value["id"] != expected_id:
                    raise ValueError("Response ID differs from requested ID")

                if name == "setup /api/challenges":
                    self.prepare(value)
            except (ValueError, TypeError, KeyError, OverflowError) as exc:
                response.failure(str(exc))

                return None

            return value

    def prepare(self, value):
        if not value["items"]:
            raise ValueError("Load preparation: empty database; import a podium CSV first")

        self.challenge_ids = [row["id"] for row in value["items"]]
        self.team_ids = sorted({p["team_id"] for row in value["items"] for p in row["placements"]})
        if not self.team_ids:
            raise ValueError("Load preparation: no podium teams in sampled challenges")

        dates = [
            datetime.fromisoformat(row["end_at"]).astimezone(UTC).date().isoformat()
            for row in value["items"]
        ]
        self.medal_variants = cycle(
            [
                ("all", {}),
                ("project", {"challenge_type": "project"}),
                ("team", {"challenge_type": "team"}),
                ("period", {"from": min(dates), "to": max(dates)}),
            ]
        )
        self.list_variants = cycle(
            [
                ("first size=10", {"page": 1, "size": 10}),
                ("last size=10", {"page": max(1, (value["total"] + 9) // 10), "size": 10}),
                ("first size=50", {"page": 1, "size": 50}),
                ("first size=200", {"page": 1, "size": 200}),
                ("project", {"challenge_type": "project"}),
                ("team", {"challenge_type": "team"}),
            ]
        )

    def on_start(self):
        initial_page = self.get_checked(
            "/api/challenges", "setup /api/challenges", page, {"page": 1, "size": 200}
        )
        if initial_page is None:
            self.environment.load_preparation_failed = True
            logger.error("Load preparation failed: check setup request failures; user stopped")
            raise StopUser()

    @task(5)
    def medals(self):
        variant, params = next(self.medal_variants)
        self.get_checked("/api/medals", f"/api/medals [{variant}]", medal_table, params)

    @task(3)
    def challenges(self):
        variant, params = next(self.list_variants)
        self.get_checked("/api/challenges", f"/api/challenges [{variant}]", page, params)

    @task(2)
    def challenge_card(self):
        # Non-security sampling of public IDs to distribute workload.
        identifier = random.choice(self.challenge_ids)  # nosec B311
        self.get_checked(
            f"/api/challenges/{identifier}",
            "/api/challenges/{id}",
            challenge,
            expected_id=identifier,
        )

    @task(2)
    def team_card(self):
        # Non-security sampling of public IDs to distribute workload.
        identifier = random.choice(self.team_ids)  # nosec B311
        self.get_checked(
            f"/api/teams/{identifier}", "/api/teams/{id}", team, expected_id=identifier
        )

    @task(1)
    def health_check(self):
        self.get_checked("/health", "/health", health)
