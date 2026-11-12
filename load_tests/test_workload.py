"""Explicit HTTP checks: python -m unittest discover -s load_tests -v."""

# Import Locust before networking modules: its gevent patch must happen first.
import locust  # noqa: F401, I001

import json

# Only runs this interpreter's Locust with explicit argument lists; no shell commands.
import subprocess  # nosec B404
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs

from gevent.pywsgi import WSGIServer
from locust.env import Environment
from locust.exception import StopUser
from locustfile import OlympicUser, fail_exit_code, reset_run

ROOT = Path(__file__).resolve().parents[1]
CHALLENGE = dict(
    id=73,
    challenge_type="project",
    name="Sample",
    project_name=None,
    start_at="2025-01-01T00:00:00Z",
    end_at="2025-02-01T00:00:00Z",
    url="https://www.boincstats.com/unused",
    placements=[dict(team_id=91, team_name="Sample", place=1, score=None)],
)


class WorkloadTests(unittest.TestCase):
    def setUp(self):
        self.mode = "ok"
        self.requests = []
        self.server = WSGIServer(("127.0.0.1", 0), self.respond, log=None)
        self.server.start()
        self.host = f"http://127.0.0.1:{self.server.server_port}"
        self.environment = Environment(user_classes=[OlympicUser], host=self.host)
        self.runner = self.environment.create_local_runner()
        reset_run(self.environment)
        OlympicUser.host = self.host
        self.user = OlympicUser(self.environment)

    def tearDown(self):
        self.user.client.close()
        self.runner.quit()
        self.server.stop()

    def respond(self, environ, start_response):
        path = environ["PATH_INFO"]
        params = parse_qs(environ["QUERY_STRING"])
        self.requests.append((environ["REQUEST_METHOD"], path, params))
        status = "200 OK"
        payload: dict[str, object] | list[dict[str, object]] = {}
        if self.mode in {"500", "503"}:
            status = self.mode + " Error"
        elif self.mode == "html":
            start_response(status, [("Content-Type", "text/html")])

            return [b"<html>broken</html>"]
        elif path == "/api/challenges":
            payload = dict(
                items=[] if self.mode == "empty" else [CHALLENGE],
                total=31,
                page=int(params.get("page", [1])[0]),
                size=int(params.get("size", [50])[0]),
            )
        elif path == "/api/challenges/73":
            payload = CHALLENGE | ({"id": 99} if self.mode == "wrong_id" else {})
        elif path == "/api/teams/91":
            payload = dict(
                id=91,
                name="Sample",
                gold=1,
                silver=0,
                bronze=0,
                total=1,
                challenges=[
                    {k: v for k, v in CHALLENGE.items() if k != "placements"} | {"place": 1}
                ],
            )
        elif path == "/api/medals":
            payload = [dict(team_id=91, team_name="Sample", gold=1, silver=0, bronze=0, total=1)]
        elif path == "/health":
            payload = {"status": "ok"}
        else:
            status = "404 Not Found"
        start_response(status, [("Content-Type", "application/json")])

        return [json.dumps(payload).encode()]

    def run_headless(self):
        # Fixed module/script and fixture-owned loopback host; no shell or external input.
        return subprocess.run(
            [  # nosec B603
                sys.executable,
                "-m",
                "locust",
                "-f",
                "load_tests/locustfile.py",
                "--host",
                self.host,
                "--headless",
                "-u",
                "1",
                "-r",
                "1",
                "-t",
                "2s",
                "--only-summary",
                "--stop-timeout",
                "1",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=25,
        )

    def test_all_variants_and_nonsequential_ids(self):
        self.user.on_start()

        for _ in range(4):
            self.user.medals()

        for _ in range(6):
            self.user.challenges()

        self.user.challenge_card()
        self.user.team_card()
        self.user.health_check()
        self.assertEqual(self.environment.stats.total.num_failures, 0)
        self.assertEqual(len(self.environment.stats.entries), 14)
        self.assertTrue(all(method == "GET" for method, _, _ in self.requests))
        self.assertIn(("GET", "/api/challenges/73", {}), self.requests)
        self.assertIn(("GET", "/api/teams/91", {}), self.requests)
        self.assertIn(("GET", "/api/challenges", {"page": ["4"], "size": ["10"]}), self.requests)
        self.assertIn(
            ("GET", "/api/medals", {"from": ["2025-02-01"], "to": ["2025-02-01"]}), self.requests
        )
        self.assertEqual(
            {
                p.get("challenge_type", [None])[0]
                for _, path, p in self.requests
                if path == "/api/medals"
            },
            {None, "project", "team"},
        )

    def test_invalid_http_json_and_id_are_failures(self):
        self.user.on_start()

        for mode in ("500", "html", "wrong_id"):
            with self.subTest(mode=mode):
                self.mode = mode
                before = self.environment.stats.total.num_failures
                self.user.challenge_card()
                self.assertEqual(self.environment.stats.total.num_failures, before + 1)

        fail_exit_code(self.environment)
        self.assertEqual(self.environment.process_exit_code, 1)

    def test_missing_structure_is_rejected(self):
        self.user.on_start()
        self.user.get_checked("/health", "invalid structure", lambda value: value["missing"])
        self.assertEqual(self.environment.stats.total.num_failures, 1)

    def test_setup_failure_stops_user_and_fails_process(self):
        for mode in ("empty", "503", "html"):
            with self.subTest(mode=mode):
                self.mode = mode

                with self.assertRaises(StopUser):
                    self.user.on_start()

                self.assertTrue(getattr(self.environment, "load_preparation_failed", False))
                result = self.run_headless()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("Load preparation failed", result.stderr)

    def test_wrong_card_id_fails_headless(self):
        # Keep startup valid, but every challenge-card response has a wrong ID.
        self.mode = "wrong_id"

        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "locustfile_card.py"
            script.write_text(
                f"import sys\nsys.path.insert(0, {str(ROOT / 'load_tests')!r})\n"
                "from locustfile import OlympicUser\n"
                "OlympicUser.tasks = [OlympicUser.challenge_card]\n"
            )
            # The temporary script is written above by this test, not supplied by a user.
            result = subprocess.run(
                [  # nosec B603
                    sys.executable,
                    "-m",
                    "locust",
                    "-f",
                    str(script),
                    "--host",
                    self.host,
                    "--headless",
                    "-u",
                    "1",
                    "-r",
                    "1",
                    "-t",
                    "2s",
                    "--only-summary",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=25,
            )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Response ID differs", result.stderr)


if __name__ == "__main__":
    unittest.main()
