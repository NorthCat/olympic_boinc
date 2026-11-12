"""Real agent transactions and serialized events, without an external APM server."""

import asyncio
import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

import pytest
from asgi_lifespan import LifespanManager
from elasticapm import Client
from elasticapm.traces import execution_context
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from olympic_boinc import apm, scheduler
from olympic_boinc.api.app import create_app
from olympic_boinc.config import Settings
from olympic_boinc.sync import SyncResult, SyncStatus


class RecordingTransport(apm.BoundedTransport):
    def __init__(self, *args, **kwargs):
        self.events = []
        super().__init__(*args, **kwargs)

    def send(self, data, forced_flush=False, custom_url=None, custom_headers=None):
        if data:
            self.events.extend(
                json.loads(line) for line in gzip.decompress(data).decode().splitlines()
            )


def settings(**kwargs):
    return Settings(
        _env_file=None,
        **{
            "database_url": "postgresql+asyncpg://u:p@db/x",
            "scheduler_enabled": False,
            "apm_enabled": True,
            **kwargs,
        },
    )


@pytest.fixture
def clients(monkeypatch):
    created = []

    def record(config):
        client = Client(
            {**config, "TRANSPORT_CLASS": "tests.test_apm.RecordingTransport"},
            server_version=(9, 5, 6),
        )
        created.append(client)

        return client

    monkeypatch.setattr(apm, "Client", record)
    yield created

    for client in created:
        client.close()


def events(client, kind):
    client.config.transport.flush()

    return [event[kind] for event in client.config.transport.events if kind in event]


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan")])
def test_invalid_sampling(value):
    with pytest.raises(ValidationError):
        settings(apm_transaction_sample_rate=value)


@pytest.mark.parametrize("value", ["", "   ", "service/name"])
def test_invalid_service_name(value):
    with pytest.raises(ValidationError):
        settings(apm_service_name=value)


@pytest.mark.parametrize("value", ["ftp://host", "http://user:password@host", "missing"])
def test_invalid_apm_url(value):
    with pytest.raises(ValidationError):
        settings(apm_server_url=value)


def test_apm_env_and_dotenv(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "OLYMPIC_DATABASE_URL=postgresql+asyncpg://u:p@db/x\n"
        "OLYMPIC_APM_ENABLED=true\n"
        "OLYMPIC_APM_ENVIRONMENT=file\n"
        "OLYMPIC_APM_SECRET_TOKEN=secret-sentinel\n"
    )
    monkeypatch.setenv("OLYMPIC_APM_ENVIRONMENT", "override")
    s = Settings(_env_file=env)

    assert s.apm_enabled and s.apm_environment == "override"
    assert "secret-sentinel" not in repr(s)
    assert s.apm_secret_token is not None
    assert s.apm_secret_token.get_secret_value() == "secret-sentinel"


def test_disabled_creates_no_client(monkeypatch):
    factory = Mock(side_effect=AssertionError("must not create agent"))
    monkeypatch.setattr(apm, "Client", factory)

    assert apm.create_client(settings(apm_enabled=False)) is None

    factory.assert_not_called()


async def test_lifecycle_disabled_and_repeated_clients(clients):
    for enabled in (False, True, True):
        app = create_app(settings(apm_enabled=enabled))

        async with LifespanManager(app):
            client = app.state.apm_client

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as http:
                assert (await http.get("/")).status_code == 200

            if enabled:
                assert len(events(client, "transaction")) == 1
                assert client.config.transport._event_queue.maxsize == 500

        assert app.state.apm_client is None

        if enabled:
            assert client.config.transport._closed

    assert len(clients) == 2


async def test_http_routes_errors_and_concurrent_contexts(clients):
    app = FastAPI()
    app.state.apm_client = apm.create_client(settings(apm_secret_token="secret-sentinel"))
    app.add_middleware(apm.APMMiddleware)

    @app.get("/items/{item_id}")
    async def item(item_id: int):
        await asyncio.sleep(0.01)

        return {"id": item_id}

    @app.post("/broken")
    async def broken():
        raise RuntimeError("secret-sentinel postgresql+asyncpg://user:db-sentinel@db/name")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as http:
        responses = await asyncio.gather(http.get("/items/1?q=a"), http.get("/items/2?q=b"))

        assert all(r.status_code == 200 for r in responses)
        assert (await http.get("/items/nope")).status_code == 422
        assert (await http.get("/unknown")).status_code == 404
        assert (await http.get("/health")).status_code == 404
        assert (await http.get("/static/styles.css")).status_code == 404
        assert (
            await http.post(
                "/broken",
                json={"private": "body-sentinel"},
                headers={
                    "Authorization": "Bearer auth-sentinel",
                    "Cookie": "session=cookie-sentinel",
                },
            )
        ).status_code == 500

    transactions = events(clients[0], "transaction")

    assert len(transactions) == 5
    assert [t["name"] for t in transactions].count("GET /items/{item_id}") == 3
    assert len({t["id"] for t in transactions}) == 5
    assert {t["result"] for t in transactions} == {"HTTP 2xx", "HTTP 4xx", "HTTP 5xx"}

    errors = events(clients[0], "error")

    assert len(errors) == 1

    failed = next(t for t in transactions if t["name"] == "POST /broken")

    assert errors[0]["transaction_id"] == failed["id"]

    payload = json.dumps(clients[0].config.transport.events)

    for sentinel in (
        "secret-sentinel",
        "db-sentinel",
        "body-sentinel",
        "auth-sentinel",
        "cookie-sentinel",
    ):
        assert sentinel not in payload

    assert errors[0]["exception"]["type"] == "RuntimeError"


@pytest.mark.parametrize("state", list(SyncStatus))
async def test_sync_status_and_counters(clients, monkeypatch, state):
    client = apm.create_client(settings())
    fetcher = Mock()

    async def close():
        pass

    fetcher.aclose = close
    monkeypatch.setattr(scheduler, "create_fetcher", lambda s: fetcher)

    async def run(*args):
        return SyncResult(status=state, added=2, skipped=3, deferred=4)

    monkeypatch.setattr(scheduler, "run_sync", run)
    await scheduler.sync_job(async_sessionmaker(), settings(), client)
    (transaction,) = events(client, "transaction")

    assert (transaction["name"], transaction["type"], transaction["result"]) == (
        "sync",
        "background",
        state.value,
    )
    assert transaction["outcome"] == ("success" if state == SyncStatus.OK else "failure")
    assert transaction["context"]["custom"] == {"added": 2, "skipped": 3, "deferred": 4}


@pytest.mark.parametrize("exception", [RuntimeError, asyncio.CancelledError])
async def test_sync_creation_failure_and_cancellation(clients, monkeypatch, exception):
    client = apm.create_client(settings())

    def fail(s):
        raise exception()

    monkeypatch.setattr(scheduler, "create_fetcher", fail)
    if exception is asyncio.CancelledError:
        with pytest.raises(asyncio.CancelledError):
            await scheduler.sync_job(async_sessionmaker(), settings(), client)
    else:
        await scheduler.sync_job(async_sessionmaker(), settings(), client)
    (transaction,) = events(client, "transaction")

    assert transaction["result"] == (
        "cancelled" if exception is asyncio.CancelledError else "failed"
    )
    assert len(events(client, "error")) == (0 if exception is asyncio.CancelledError else 1)


async def test_http_cancel_finishes_transaction(clients):
    client = apm.create_client(settings())
    app = FastAPI()
    app.state.apm_client = client
    app.add_middleware(apm.APMMiddleware)

    @app.get("/cancel")
    async def cancel():
        raise asyncio.CancelledError()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        with pytest.raises(asyncio.CancelledError):
            await http.get("/cancel")

    (transaction,) = events(client, "transaction")

    assert transaction["result"] == "cancelled"
    assert execution_context.get_transaction() is None


def test_apm_failures_are_isolated(monkeypatch, caplog):
    monkeypatch.setattr(apm, "Client", Mock(side_effect=RuntimeError("private-secret")))

    assert apm.create_client(settings()) is None
    assert apm.safely(Mock(side_effect=ValueError("private-secret"))) is None
    assert "private-secret" not in caplog.text


@pytest.fixture
def intake():
    payloads: list[dict] = []
    state = {"status": 503}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if state["status"] == 202:
                payloads.extend(
                    json.loads(line) for line in gzip.decompress(payload).decode().splitlines()
                )
            self.send_response(state["status"])
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state, payloads
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


async def test_transport_failure_auth_and_recovery_do_not_break_app(intake, database_url, engine):
    url, state, payloads = intake
    app = create_app(settings(database_url=database_url, apm_server_url=url))

    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            for status in (503, 401, 202):
                state["status"] = status
                if status == 202:
                    await asyncio.sleep(
                        1.1
                    )  # Respect the real agent's backoff after two transport failures.

                assert (await http.get("/api/medals")).status_code == 200
                assert (await http.get("/health")).status_code == 200

                await asyncio.to_thread(app.state.apm_client.config.transport.flush)

    assert any(event.get("transaction", {}).get("name") == "GET /api/medals" for event in payloads)


async def test_absent_receiver_is_not_startup_dependency(database_url):
    app = create_app(settings(database_url=database_url, apm_server_url="http://127.0.0.1:1"))

    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            assert (await http.get("/")).status_code == 200
            assert (await http.get("/health")).status_code == 200


async def test_broken_adapter_does_not_change_http(clients, monkeypatch):
    app = create_app(settings())

    async with LifespanManager(app):
        monkeypatch.setattr(
            app.state.apm_client, "begin_transaction", Mock(side_effect=RuntimeError())
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            assert (await http.get("/")).status_code == 200


@pytest.mark.parametrize("phase", ["run", "close"])
async def test_sync_error_after_creation_closes_fetcher(clients, monkeypatch, phase):
    client = apm.create_client(settings())
    closed = []

    async def close():
        closed.append(True)
        if phase == "close":
            raise RuntimeError("closing")

    fetcher = Mock(aclose=close)
    monkeypatch.setattr(scheduler, "create_fetcher", lambda s: fetcher)

    async def run(*args):
        if phase == "run":
            raise RuntimeError("running")

        return SyncResult()

    monkeypatch.setattr(scheduler, "run_sync", run)
    await scheduler.sync_job(async_sessionmaker(), settings(), client)

    assert closed == [True]

    (transaction,) = events(client, "transaction")

    assert transaction["result"] == "failed"
    assert len(events(client, "error")) == 1


async def test_shutdown_error_and_timeout(monkeypatch):
    await apm.close_client(None)
    await apm.close_client(Mock(close=Mock(side_effect=RuntimeError())))

    async def timeout(*args, **kwargs):
        args[0].close()
        raise TimeoutError()

    # Replace to_thread, so the simulated timeout creates no orphan coroutine/thread.
    monkeypatch.setattr(apm.asyncio, "to_thread", lambda fn, *a: Mock(close=lambda: None))
    monkeypatch.setattr(apm.asyncio, "wait_for", timeout)
    await apm.close_client(Mock())


@pytest.mark.parametrize("sample_rate", [0.0, 1.0])
async def test_sql_spans_http_concurrency_and_redaction(clients, database_url, sample_rate):
    app = create_app(settings(database_url=database_url, apm_transaction_sample_rate=sample_rate))

    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            responses = await asyncio.gather(
                http.get("/api/medals"), http.get("/api/challenges/years")
            )

            assert all(response.status_code == 200 for response in responses)
            assert (await http.get("/health")).status_code == 200

        transactions = events(clients[0], "transaction")
        spans = events(clients[0], "span")
        if sample_rate:
            assert len(transactions) == 2
            assert {span["transaction_id"] for span in spans} == {t["id"] for t in transactions}
            assert all(span["type"] == "db" and span["subtype"] == "postgresql" for span in spans)
            assert all(span["duration"] >= 0 and span["outcome"] == "success" for span in spans)

            statements = [span["context"]["db"]["statement"] for span in spans]

            assert all("SELECT" in statement for statement in statements)
            assert any("challenge" in statement for statement in statements)
        else:
            assert not transactions  # Modern APM servers discard unsampled transactions.
            assert not spans


async def test_sql_error_cleanup_background_and_private_values(clients, database_url):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from olympic_boinc.db import create_engine

    client = apm.create_client(settings())

    assert client is not None

    engine = create_engine(database_url)
    apm.instrument_database(engine, client)

    try:
        # Queries outside transactions must not create orphan spans.
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        transaction = apm.Transaction(client, "background", "sync")
        transaction.start()

        async with engine.connect() as conn:
            assert (
                await conn.scalar(text("SELECT :value"), {"value": "parameter-sentinel"})
                == "parameter-sentinel"
            )

            await conn.execute(text("/* comment-sentinel */ SELECT 'literal-sentinel'"))

            with pytest.raises(DBAPIError):
                await conn.execute(text("SELECT 1 / 0 /* error-sentinel */"))

            await conn.rollback()
            await conn.execute(text("SELECT 2"))

        assert execution_context.get_span() is None

        transaction.finish()
        spans = events(client, "span")

        assert len(spans) == 4
        assert [s["name"] for s in spans] == ["SELECT", "SQL", "SELECT", "SELECT"]
        assert [s["outcome"] for s in spans] == ["success", "success", "failure", "success"]
        assert [s["context"]["db"]["statement"] for s in spans] == [
            "SELECT $1",
            "SELECT ?",
            "SELECT ? / ?",
            "SELECT ?",
        ]

        (parent,) = events(client, "transaction")

        assert all(s["parent_id"] == parent["id"] for s in spans)

        payload = json.dumps(client.config.transport.events)

        for secret in (
            "parameter-sentinel",
            "literal-sentinel",
            "comment-sentinel",
            "error-sentinel",
            database_url,
        ):
            assert secret not in payload
    finally:
        await engine.dispose()


async def test_sql_instrumentation_disabled_and_failure_isolated(
    clients, database_url, monkeypatch
):
    from sqlalchemy import text

    from olympic_boinc.db import create_engine

    engine = create_engine(database_url)

    try:
        apm.instrument_database(engine, None)

        assert not engine.sync_engine.dispatch.before_cursor_execute

        client = apm.create_client(settings())
        apm.instrument_database(engine, client)
        monkeypatch.setattr(
            apm.elasticapm, "capture_span", Mock(side_effect=RuntimeError("private-secret"))
        )

        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT 1")) == 1
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        (
            "SELECT team2.id FROM team2 WHERE id = $1::INTEGER",
            "SELECT team2.id FROM team2 WHERE id = $1::INTEGER",
        ),
        (
            'SELECT "some  table"."column1" WHERE id = :id',
            'SELECT "some  table"."column1" WHERE id = :id',
        ),
        (
            "SELECT 'it''s private', E'back\\'slash', N'private', U&'private', B'101', X'ff'",
            "SELECT ?, ?, ?, ?, ?, ?",
        ),
        ("SELECT $$secret$$, $tag$secret ' quoted$tag$, $1", "SELECT ?, ?, $1"),
        (
            "SELECT 123, -4.5, .75, 1e-10, 0xABC, 0o777, 0b101, 1_234",
            "SELECT ?, -?, ?, ?, ?, ?, ?, ?",
        ),
        (
            "SELECT/* outer /* inner-secret */ private */id -- private\nFROM teams",
            "SELECT id \nFROM teams",
        ),
        ("SELECT 'private", "SELECT ?"),
        ("SELECT 'private\\", "SELECT ?"),
        ("SELECT $tag$private", "SELECT ?"),
        ("SELECT 1 /* private", "SELECT ?"),
        ("SELECT %(id)s, %s, ?", "SELECT %(id)s, %s, ?"),
        ("", ""),
    ],
)
def test_sql_statement_preserves_structure_without_values(statement, expected):
    assert apm.sql_statement(statement) == expected


def test_sql_statement_limits_payload_after_redaction():
    statement = "SELECT '" + "private" * 2000 + "', " + "column_name, " * 2000
    sanitized = apm.sql_statement(statement)

    assert len(sanitized) == 10000
    assert sanitized.startswith("SELECT ?, column_name, ")
    assert "private" not in sanitized


def test_sql_tokenizer_failure_does_not_leak_statement(monkeypatch):
    monkeypatch.setattr(apm, "SQL_TOKEN", Mock(match=Mock(return_value=None)))

    assert apm.sql_statement("SELECT 'private-value'") == "[REDACTED SQL]"
