"""App-owned Elastic APM integration using public transaction APIs and pure ASGI."""

import asyncio
import logging
import queue
import re
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

import elasticapm
from elasticapm import Client
from elasticapm.transport.http import Transport
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from olympic_boinc.config import Settings

logger = logging.getLogger(__name__)
URL_CREDENTIALS = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/'\"]*:[^\s/'\"]*@[^\s'\"]*")
SQL_TOKEN = re.compile(
    r"(?P<string>(?:[eEbBxXnN]|[uU]&)?'(?:''|\\(?:[\s\S]|\Z)|[^'\\])*(?:'|\Z))"
    r'|(?P<identifier>"(?:""|[^"])*(?:"|\Z))'
    r"|(?P<dollar>\$(?:[^\W\d]\w*)?\$)"
    r"|(?P<parameter>\$\d+|:[a-zA-Z_]\w*|%\([^)]+\)s|%s|\?)"
    r"|(?P<number>(?:0[xX][\da-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+"
    r"|(?:\d[\d_]*(?:\.[\d_]*)?|\.\d[\d_]*)(?:[eE][+-]?[\d_]+)?))"
    r"|(?P<word>[^\W\d][\w$]*)|(?P<other>[\s\S])"
)
SENSITIVE_EVENT_FIELDS = {
    "body",
    "headers",
    "cookies",
    "vars",
    "authorization",
    "secret_token",
    "database_url",
}


def _skip_block_comment(statement: str, position: int) -> int:
    """Find the end of a possibly nested PostgreSQL block comment."""
    depth = 1
    position += 2

    while position < len(statement) and depth:
        if statement.startswith("/*", position):
            depth += 1
            position += 2
        elif statement.startswith("*/", position):
            depth -= 1
            position += 2
        else:
            position += 1

    return position


def sql_statement(statement: str) -> str:
    """Keep PostgreSQL structure and placeholders; strip comments and literal values."""
    output: list[str] = []
    position = 0

    while position < len(statement):
        if statement.startswith("--", position):
            end = statement.find("\n", position + 2)
            position = len(statement) if end < 0 else end + 1
            output.append("\n")
            continue
        if statement.startswith("/*", position):
            position = _skip_block_comment(statement, position)
            output.append(" ")
            continue

        token = SQL_TOKEN.match(statement, position)
        if token is None:
            # Fail closed if the tokenizer stops covering every character.
            return "[REDACTED SQL]"

        position = token.end()
        if token.lastgroup == "dollar":
            end = statement.find(token.group(), position)
            position = len(statement) if end < 0 else end + len(token.group())
            output.append("?")
        elif token.lastgroup in {"string", "number"}:
            output.append("?")
        else:
            output.append(token.group())

    return "".join(output).strip()[:10000]


class BoundedTransport(Transport):
    """The agent's HTTP transport with a small, nonblocking event queue."""

    def _init_event_queue(self, chill_until, max_chill_time):
        return queue.Queue(maxsize=500)


def sanitize_event(client: Client, event: dict) -> dict:
    """Remove unneeded request/frame data and redact credentials before serialization."""
    token = client.config.secret_token

    def clean(value):
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if key.lower() not in SENSITIVE_EVENT_FIELDS
            }
        if isinstance(value, list):
            return [clean(item) for item in value]

        if isinstance(value, str):
            value = URL_CREDENTIALS.sub("[REDACTED URL]", value)

            return value.replace(token, "[REDACTED]") if token else value

        return value

    return clean(event)


def create_client(settings: Settings) -> Client | None:
    if not settings.apm_enabled:
        return None

    try:
        secret_token = (
            settings.apm_secret_token.get_secret_value() if settings.apm_secret_token else None
        )

        return Client(
            {
                "SERVICE_NAME": settings.apm_service_name,
                "SERVICE_VERSION": version("olympic-boinc"),
                "ENVIRONMENT": settings.apm_environment,
                "SERVER_URL": settings.apm_server_url,
                "SECRET_TOKEN": secret_token,
                "TRANSACTION_SAMPLE_RATE": settings.apm_transaction_sample_rate,
                "TRANSPORT_CLASS": "olympic_boinc.apm.BoundedTransport",
                "SERVER_TIMEOUT": "2s",
                "API_REQUEST_TIME": "5s",
                "CENTRAL_CONFIG": False,
                "CLOUD_PROVIDER": "none",
                "METRICS_INTERVAL": "0s",
                "BREAKDOWN_METRICS": False,
                "DISABLE_LOG_RECORD_FACTORY": True,
                "CAPTURE_BODY": "off",
                "CAPTURE_HEADERS": False,
                "COLLECT_LOCAL_VARIABLES": "off",
                "SOURCE_LINES_ERROR_APP_FRAMES": 0,
                "SOURCE_LINES_ERROR_LIBRARY_FRAMES": 0,
                "PROCESSORS": ["olympic_boinc.apm.sanitize_event"],
            }
        )
    except Exception as exc:
        logger.error("APM initialization failed (%s)", type(exc).__name__)

        return None


def safely(function, *args, **kwargs) -> Any:
    """Telemetry errors must never replace the application's result or expose secrets."""
    try:
        return function(*args, **kwargs)
    except Exception as exc:
        logger.error("APM operation failed (%s)", type(exc).__name__)

        return None


async def close_client(client: Client | None) -> None:
    if client is not None:
        try:
            await asyncio.wait_for(asyncio.to_thread(safely, client.close), timeout=5)
        except TimeoutError:
            logger.warning("APM shutdown timed out")


def instrument_database(engine: AsyncEngine, client: Client | None) -> None:
    """Trace this engine with sanitized SQL; never collect parameters or connection URLs."""
    if client is None:
        return

    def before_execute(conn, cursor, statement, parameters, context, executemany):
        # Use a fixed vocabulary: even literal SQL and comments may contain secrets.
        words = statement.split(None, 1)
        operation = words[0].upper() if words else "SQL"
        if operation not in {"SELECT", "INSERT", "UPDATE", "DELETE", "WITH"}:
            operation = "SQL"

        span = elasticapm.capture_span(
            operation,
            span_type="db",
            span_subtype="postgresql",
            span_action="query",
            leaf=True,
            extra={"db": {"type": "sql", "statement": sql_statement(statement)}},
        )
        if span.__enter__() is not None:
            context._olympic_apm_span = span

    def finish(context, error=None):
        if context is None:
            return

        span = getattr(context, "_olympic_apm_span", None)
        if span is None:
            return

        context._olympic_apm_span = None
        error_type = type(error) if error is not None else None
        safely(span.__exit__, error_type, error, None)

    def after_execute(conn, cursor, statement, parameters, context, executemany):
        finish(context)

    def handle_error(context):
        finish(context.execution_context, context.original_exception)

    event.listen(
        engine.sync_engine, "before_cursor_execute", lambda *args: safely(before_execute, *args)
    )
    event.listen(engine.sync_engine, "after_cursor_execute", after_execute)
    event.listen(engine.sync_engine, "handle_error", handle_error)


@dataclass
class Transaction:
    client: Client | None
    kind: str
    name: str
    result: str = "failed"
    outcome: str = "failure"
    active: bool = False

    def start(self) -> None:
        if self.client is not None:
            self.active = safely(self.client.begin_transaction, self.kind) is not None

    def capture_exception(self) -> None:
        if self.active and self.client is not None:
            safely(self.client.capture_exception)

    def context(self, values: dict) -> None:
        if self.active:
            safely(elasticapm.set_custom_context, values)

    def finish(self) -> None:
        if self.active and self.client is not None:
            safely(elasticapm.set_transaction_outcome, self.outcome)
            safely(self.client.end_transaction, self.name, self.result)
            self.active = False


class APMMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        excluded_path = path in {"/health", "/static"} or path.startswith("/static/")
        if scope["type"] != "http" or excluded_path:
            await self.app(scope, receive, send)
            return

        transaction = Transaction(
            getattr(scope["app"].state, "apm_client", None), "request", "unknown route"
        )
        transaction.start()
        status = 500

        async def response(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, response)
            transaction.result = f"HTTP {status // 100}xx"
            transaction.outcome = "failure" if status >= 500 else "success"
        except asyncio.CancelledError:
            transaction.result, transaction.outcome = "cancelled", "unknown"
            raise
        except Exception:
            transaction.result = "HTTP 5xx"
            transaction.capture_exception()
            raise
        finally:
            route = scope.get("route")
            transaction.name = f"{scope['method']} {getattr(route, 'path', 'unknown route')}"
            transaction.finish()
