"""Idempotently install the pinned, bundled APM assets, without a package registry."""

import base64
import json
import os
import time
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

VERSION = "9.5.6"


def _has_invalid_url_characters(value: str) -> bool:
    return any(
        character.isspace() or ord(character) < 32 or ord(character) == 127 or character == "\\"
        for character in value
    )


def _request_endpoint(base: str, path: str) -> tuple[str, str, str, int | None]:
    """Validate an endpoint before preparing credentials or opening a connection."""
    try:
        endpoint = urlsplit(base)
        port = endpoint.port
        hostname = endpoint.hostname
        has_credentials = endpoint.username is not None or endpoint.password is not None
        has_url_parameters = bool(endpoint.query or endpoint.fragment)
        invalid_request_path = not path.startswith("/") or path.startswith("//")

        if (
            endpoint.scheme not in {"http", "https"}
            or not hostname
            or has_credentials
            or has_url_parameters
            or invalid_request_path
            or _has_invalid_url_characters(base)
            or _has_invalid_url_characters(path)
        ):
            raise ValueError("Invalid endpoint")
    except ValueError:
        raise ValueError(
            "APM setup requires an HTTP(S) URL without credentials, query or fragment "
            "and an absolute request path"
        ) from None

    return endpoint.scheme, hostname, endpoint.path, port


def request(path: str, data: bytes | None = None, *, elastic: bool = False) -> dict:
    base = (
        "http://elasticsearch:9200"
        if elastic
        else os.environ.get("APM_SETUP_KIBANA_URL", "http://kibana:5601")
    )
    scheme, hostname, base_path, port = _request_endpoint(base, path)

    headers = {"kbn-xsrf": "apm-setup", "Content-Type": "application/json"}
    credentials = base64.b64encode(f"elastic:{os.environ['ELASTIC_PASSWORD']}".encode()).decode()
    headers["Authorization"] = f"Basic {credentials}"

    connection_type = HTTPSConnection if scheme == "https" else HTTPConnection
    connection = connection_type(hostname, port=port, timeout=10)

    try:
        connection.request(
            "POST" if data is not None else "GET",
            base_path.rstrip("/") + path,
            body=data,
            headers=headers,
        )
        response = connection.getresponse()
        # http.client never follows redirects: credentials stay on the configured endpoint.
        if not 200 <= response.status < 300:
            raise HTTPError(
                base + path, response.status, "APM setup HTTP status", response.headers, None
            )

        return json.load(response)
    except HTTPError:
        raise
    except (OSError, HTTPException) as exc:
        raise URLError("APM setup HTTP request failed") from exc
    finally:
        connection.close()


def _configure_service_credentials() -> None:
    role = {
        "cluster": ["monitor", "read_ilm", "read_pipeline"],
        "indices": [
            {
                "names": ["traces-apm*", "logs-apm*", "metrics-apm*"],
                "privileges": ["auto_configure", "create_doc", "view_index_metadata"],
            },
            {
                "names": [".apm-agent-configuration"],
                "privileges": ["read"],
                "allow_restricted_indices": True,
            },
        ],
    }
    writer = {"password": os.environ["APM_WRITER_PASSWORD"], "roles": ["apm_writer"]}

    request(
        "/_security/user/kibana_system/_password",
        json.dumps({"password": os.environ["KIBANA_SYSTEM_PASSWORD"]}).encode(),
        elastic=True,
    )
    request("/_security/role/apm_writer", json.dumps(role).encode(), elastic=True)
    request("/_security/user/apm_writer", json.dumps(writer).encode(), elastic=True)

    print("Elastic service credentials are configured", flush=True)


def _install_integration() -> None:
    package_path = f"/api/fleet/epm/packages/apm/{VERSION}"
    request("/api/status")

    try:
        info = request(package_path)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        info = {}

    installation = info.get("item", {}).get("status") or info.get("status")
    if installation != "installed":
        # Kibana resolves the pinned version from its bundled air-gapped packages.
        request(package_path, b'{"force":false}')

    info = request(package_path)
    confirmed_status = info.get("item", {}).get("status") or info.get("status")
    if confirmed_status != "installed":
        raise RuntimeError("APM assets are not installed")

    print(f"APM integration {VERSION} is installed", flush=True)


def run() -> None:
    required = [
        "ELASTIC_PASSWORD",
        "KIBANA_SYSTEM_PASSWORD",
        "APM_WRITER_PASSWORD",
        "KIBANA_ENCRYPTION_KEY",
    ]
    if any(not os.environ.get(name) for name in required):
        raise SystemExit(
            "Set Elastic passwords and KIBANA_ENCRYPTION_KEY in .docker-env (see README)"
        )
    if len(os.environ["KIBANA_ENCRYPTION_KEY"]) < 32:
        raise SystemExit("KIBANA_ENCRYPTION_KEY must contain at least 32 characters")

    for attempt in range(30):
        try:
            if os.environ.get("APM_SETUP_PHASE") == "credentials":
                _configure_service_credentials()
            else:
                _install_integration()

            return
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            # Only the exception type/status; never credentials or returned response bodies.
            exception_type = type(exc).__name__
            status_code = getattr(exc, "code", "")
            print(
                f"APM setup attempt {attempt + 1}/30 failed: {exception_type} {status_code}",
                flush=True,
            )
            time.sleep(2)

    raise SystemExit("APM integration setup failed; inspect Kibana logs")


if __name__ == "__main__":
    run()
