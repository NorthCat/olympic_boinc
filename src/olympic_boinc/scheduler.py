"""In-process scheduler that runs the challenge sync on a cron schedule (UTC)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from elasticapm import Client
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from olympic_boinc.apm import Transaction
from olympic_boinc.config import Settings
from olympic_boinc.scraper.fetcher import create_fetcher
from olympic_boinc.sync import run_sync

logger = logging.getLogger(__name__)

SYNC_JOB_ID = "sync"
# Include job boundaries, requested URLs, individual errors and the run summary.
SYNC_LOGGERS = (
    "apscheduler",
    "olympic_boinc.scheduler",
    "olympic_boinc.sync",
    "olympic_boinc.scraper",
)
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def open_sync_log(path: Path) -> logging.Handler:
    """Add a rotating file for sync loggers at INFO and up, preserving stderr output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    for name in SYNC_LOGGERS:
        sync_logger = logging.getLogger(name)
        sync_logger.addHandler(handler)
        if sync_logger.getEffectiveLevel() > logging.INFO:
            sync_logger.setLevel(logging.INFO)

    return handler


def close_sync_log(handler: logging.Handler) -> None:
    for name in SYNC_LOGGERS:
        logging.getLogger(name).removeHandler(handler)

    handler.close()


async def sync_job(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    apm_client: Client | None = None,
) -> None:
    """One scheduled run; the browser lives only for this run and is closed whatever the outcome."""
    logger.info("sync job started")
    transaction = Transaction(apm_client, "background", "sync")
    transaction.start()

    try:
        fetcher = create_fetcher(settings)

        try:
            result = await run_sync(session_factory, fetcher, settings)
            if result is not None:
                transaction.result = result.status.value
                transaction.outcome = "success" if transaction.result == "ok" else "failure"
                transaction.context(
                    {"added": result.added, "skipped": result.skipped, "deferred": result.deferred}
                )
        finally:
            await fetcher.aclose()
    except asyncio.CancelledError:
        transaction.result, transaction.outcome = "cancelled", "unknown"
        raise
    except Exception:
        transaction.result, transaction.outcome = "failed", "failure"
        transaction.capture_exception()
        logger.exception("sync job failed")
    finally:
        transaction.finish()


def build_scheduler(settings: Settings, job: Callable[[], Awaitable[None]]) -> AsyncIOScheduler:
    """Scheduler with `job` on `sync_cron`; runs never overlap and missed ones collapse into one.

    With `sync_on_startup`, the same job runs once immediately after startup,
    then follows `sync_cron`.
    """
    scheduler = AsyncIOScheduler(timezone=UTC)
    first_run = {"next_run_time": datetime.now(UTC)} if settings.sync_on_startup else {}
    scheduler.add_job(
        job,
        CronTrigger.from_crontab(settings.sync_cron, timezone=UTC),
        id=SYNC_JOB_ID,
        name=SYNC_JOB_ID,
        max_instances=1,
        coalesce=True,
        **first_run,
    )

    return scheduler
