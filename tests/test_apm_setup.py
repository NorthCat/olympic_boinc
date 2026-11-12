"""Bootstrap contract without Docker, a registry or actual credentials."""

import importlib.util
import json
import threading
from base64 import b64encode
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TypedDict
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

SPEC = importlib.util.spec_from_file_location(
    "apm_setup", Path(__file__).parents[1] / "docker/apm-setup.py"
)
assert SPEC is not None and SPEC.loader is not None
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class IntakeState(TypedDict):
    status: int
    location: str


@pytest.fixture
def credentials(monkeypatch):
    for name in ("ELASTIC_PASSWORD", "KIBANA_SYSTEM_PASSWORD", "APM_WRITER_PASSWORD"):
        monkeypatch.setenv(name, "test-password")

    monkeypatch.setenv("KIBANA_ENCRYPTION_KEY", "test-encryption-key-with-32-characters")
    monkeypatch.delenv("APM_SETUP_PHASE", raising=False)


def test_credentials_phase(credentials, monkeypatch):
    monkeypatch.setenv("APM_SETUP_PHASE", "credentials")
    request = Mock(return_value={})
    monkeypatch.setattr(setup, "request", request)
    setup.run()

    assert [c.args[0] for c in request.call_args_list] == [
        "/_security/user/kibana_system/_password",
        "/_security/role/apm_writer",
        "/_security/user/apm_writer",
    ]

    role = json.loads(request.call_args_list[1].args[1])

    assert "superuser" not in str(role)
    assert "create_doc" in role["indices"][0]["privileges"]
    assert role["indices"][1] == {
        "names": [".apm-agent-configuration"],
        "privileges": ["read"],
        "allow_restricted_indices": True,
    }


def test_already_installed_is_idempotent(credentials, monkeypatch):
    request = Mock(return_value={"item": {"status": "installed"}})
    monkeypatch.setattr(setup, "request", request)
    setup.run()

    assert request.call_count == 3
    assert all(len(c.args) == 1 for c in request.call_args_list)


def test_installs_pinned_bundled_package(credentials, monkeypatch):
    request = Mock(
        side_effect=[
            {},
            HTTPError("http://test", 404, "missing", Message(), None),
            {},
            {"item": {"status": "installed"}},
        ]
    )
    monkeypatch.setattr(setup, "request", request)
    setup.run()

    assert request.call_args_list[2].args == (
        "/api/fleet/epm/packages/apm/9.5.6",
        b'{"force":false}',
    )


def test_retry_is_bounded_and_does_not_log_response_secrets(credentials, monkeypatch, capsys):
    request = Mock(side_effect=HTTPError("http://test", 401, "sensitive-response", Message(), None))
    monkeypatch.setattr(setup, "request", request)
    monkeypatch.setattr(setup.time, "sleep", lambda seconds: None)

    with pytest.raises(SystemExit, match="setup failed"):
        setup.run()

    assert request.call_count == 30
    assert "sensitive-response" not in capsys.readouterr().out


def test_missing_credentials_and_short_key(credentials, monkeypatch):
    monkeypatch.setenv("KIBANA_ENCRYPTION_KEY", "short")

    with pytest.raises(SystemExit, match="32 characters"):
        setup.run()

    monkeypatch.delenv("ELASTIC_PASSWORD")

    with pytest.raises(SystemExit, match=".docker-env"):
        setup.run()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://kibana",
        "http:///api/status",
        "http://user:password-sentinel@kibana",
        "http://kibana:wrong",
        "http://[invalid",
        "http://kibana/?secret=value",
        "http://kibana/#secret",
        " http://kibana",
        "http://kibana\n",
        "http://kibana\\evil",
        "http://kibana:99999",
    ],
)
def test_invalid_url_rejected_before_connecting(credentials, monkeypatch, url):
    connect = Mock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(setup, "HTTPConnection", connect)
    monkeypatch.setattr(setup, "HTTPSConnection", connect)
    monkeypatch.setenv("APM_SETUP_KIBANA_URL", url)

    with pytest.raises(ValueError, match="HTTP.S") as exc:
        setup.request("/api/status")

    assert "password-sentinel" not in str(exc.value)

    connect.assert_not_called()


@pytest.mark.parametrize(
    "path", ["https://other.invalid/", "//other.invalid/", "/api/\nstatus", "/api/\\status"]
)
def test_invalid_request_path_rejected(credentials, path):
    with pytest.raises(ValueError, match="absolute request path"):
        setup.request(path)


@pytest.fixture
def local_intake():
    requests = []
    state: IntakeState = {"status": 200, "location": "/capture"}

    class Handler(BaseHTTPRequestHandler):
        server: ThreadingHTTPServer

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append(
                (self.server.server_port, self.command, self.path, dict(self.headers), body)
            )
            self.send_response(200 if self.path == "/capture" else state["status"])
            self.send_header("Location", state["location"])
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

        def log_message(self, *args):
            pass

    servers = [ThreadingHTTPServer(("127.0.0.1", 0), Handler) for _ in range(2)]
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in servers]

    for thread in threads:
        thread.start()

    try:
        yield [f"http://127.0.0.1:{server.server_port}" for server in servers], state, requests
    finally:
        for server, thread in zip(servers, threads, strict=True):
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


@pytest.mark.parametrize("data", [None, b'{"value":true}'])
def test_http_request_method_prefix_and_credentials(credentials, monkeypatch, local_intake, data):
    urls, _, requests = local_intake
    monkeypatch.setenv("APM_SETUP_KIBANA_URL", urls[0] + "/kibana/")

    assert setup.request("/api/status", data) == {"status": "ok"}

    _, method, path, headers, body = requests[0]

    assert method == ("GET" if data is None else "POST")
    assert path == "/kibana/api/status"
    assert headers["Authorization"] == "Basic " + b64encode(b"elastic:test-password").decode()
    assert body == (data or b"")


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401, 404])
def test_redirects_not_followed_and_http_errors_preserved(
    credentials, monkeypatch, local_intake, status
):
    urls, state, requests = local_intake
    monkeypatch.setenv("APM_SETUP_KIBANA_URL", urls[0])
    state.update(status=status, location=urls[1] + "/capture")

    with pytest.raises(HTTPError) as exc:
        setup.request("/api/status")

    assert exc.value.code == status
    assert (
        len(requests) == 1
    )  # No request (or Authorization header) reaches the redirect destination.


def test_https_selection_closes_connection_on_network_failure(credentials, monkeypatch):
    monkeypatch.setenv("APM_SETUP_KIBANA_URL", "https://kibana:5601")
    connection = Mock()
    connection.request.side_effect = OSError("private-network-error")
    factory = Mock(return_value=connection)
    monkeypatch.setattr(setup, "HTTPSConnection", factory)

    with pytest.raises(URLError, match="HTTP request failed"):
        setup.request("/api/status")

    factory.assert_called_once_with("kibana", port=5601, timeout=10)
    connection.close.assert_called_once()


def test_incomplete_installation_never_reports_success(credentials, monkeypatch, capsys):
    request = Mock(return_value={"item": {"status": "installing"}})
    monkeypatch.setattr(setup, "request", request)
    monkeypatch.setattr(setup.time, "sleep", lambda seconds: None)

    with pytest.raises(SystemExit, match="setup failed"):
        setup.run()

    assert request.call_count == 120

    output = capsys.readouterr().out

    assert "is installed" not in output
    assert "test-password" not in output
