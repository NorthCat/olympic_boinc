import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest
from apscheduler.triggers.cron import CronTrigger
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from olympic_boinc import scheduler as scheduler_module
from olympic_boinc.api.app import create_app
from olympic_boinc.config import Settings
from olympic_boinc.scheduler import (
    SYNC_JOB_ID,
    build_scheduler,
    close_sync_log,
    open_sync_log,
    sync_job,
)


def settings(**overrides) -> Settings:
    return Settings(
        _env_file=None, **{"database_url": "postgresql+asyncpg://u:p@db/x", **overrides}
    )


async def noop() -> None:
    pass


@pytest.mark.parametrize("cron", ["0 3 * * *", "*/5 * * * *"])
def test_job_is_registered_with_cron_trigger(cron):
    scheduler = build_scheduler(settings(sync_cron=cron), noop)

    job = scheduler.get_job(SYNC_JOB_ID)

    assert isinstance(job.trigger, CronTrigger)
    assert str(job.trigger) == str(CronTrigger.from_crontab(cron, timezone="UTC"))
    assert str(job.trigger.timezone) == "UTC"
    assert (job.max_instances, job.coalesce) == (1, True)
    assert job.name == SYNC_JOB_ID


def test_default_schedule_is_daily_at_3_utc():
    job = build_scheduler(settings(), noop).get_job(SYNC_JOB_ID)

    assert str(job.trigger) == "cron[month='*', day='*', day_of_week='*', hour='3', minute='0']"


class FakeFetcher:
    def __init__(self) -> None:
        self.closed = 0

    async def get(self, url: str) -> str:
        raise AssertionError("run_sync is stubbed")

    async def aclose(self) -> None:
        self.closed += 1


@pytest.fixture
def fetcher(monkeypatch) -> FakeFetcher:
    fake = FakeFetcher()
    monkeypatch.setattr(scheduler_module, "create_fetcher", lambda s: fake)

    return fake


async def test_job_runs_sync_and_closes_fetcher(monkeypatch, fetcher):
    calls = []

    async def fake_run_sync(session_factory, f, s):
        calls.append((session_factory, f, s))

    monkeypatch.setattr(scheduler_module, "run_sync", fake_run_sync)
    s = settings()

    factory = async_sessionmaker()
    await sync_job(factory, s)

    assert calls == [(factory, fetcher, s)]
    assert fetcher.closed == 1


async def test_job_survives_sync_exception_and_closes_fetcher(monkeypatch, fetcher, caplog):
    async def failing_run_sync(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "run_sync", failing_run_sync)

    factory = async_sessionmaker()
    await sync_job(factory, settings())  # does not raise
    await sync_job(factory, settings())  # the next run works as usual

    assert fetcher.closed == 2

    failures = [r for r in caplog.records if r.message == "sync job failed"]

    assert len(failures) == 2 and failures[0].levelno == logging.ERROR and failures[0].exc_info


async def test_app_serves_requests_without_scheduler(database_url):
    app = create_app(settings(database_url=database_url, scheduler_enabled=False))

    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        assert (await client.get("/openapi.json")).status_code == 200
        assert app.state.scheduler is None
        assert app.state.session_factory is not None


async def test_scheduler_starts_and_stops_with_app(database_url, fetcher, tmp_path):
    app = create_app(
        settings(
            database_url=database_url, scheduler_enabled=True, sync_log_file=tmp_path / "sync.log"
        )
    )

    async with LifespanManager(app):
        scheduler = app.state.scheduler

        assert scheduler.running
        assert scheduler.get_job(SYNC_JOB_ID).next_run_time is not None

    assert not scheduler.running
    assert fetcher.closed == 0  # no run was due, so no browser was opened


async def test_sync_log_file_gets_runs_and_urls(monkeypatch, tmp_path):
    path = tmp_path / "logs" / "sync.log"  # the directory is created
    url = "https://www.boincstats.com/stats/pchallenge/team/overview"

    async def fake_run_sync(session_factory, f, s):
        logging.getLogger("olympic_boinc.scraper.fetcher").info("GET %s", url)
        logging.getLogger("olympic_boinc.sync").warning("sync partial in 1 s: added=0")

    monkeypatch.setattr(scheduler_module, "run_sync", fake_run_sync)
    monkeypatch.setattr(scheduler_module, "create_fetcher", lambda s: FakeFetcher())
    handler = open_sync_log(path)

    try:
        await sync_job(async_sessionmaker(), settings())
        logging.getLogger("olympic_boinc.api").warning("not a sync logger")
    finally:
        close_sync_log(handler)

    logging.getLogger("olympic_boinc.sync").warning("after close")

    lines = path.read_text().splitlines()

    assert [line.split(" ", 2)[2] for line in lines] == [
        "INFO olympic_boinc.scheduler: sync job started",
        f"INFO olympic_boinc.scraper.fetcher: GET {url}",
        "WARNING olympic_boinc.sync: sync partial in 1 s: added=0",
    ]


async def test_app_writes_sync_log_only_with_scheduler(database_url, tmp_path):
    path = tmp_path / "sync.log"
    off = create_app(
        settings(database_url=database_url, scheduler_enabled=False, sync_log_file=path)
    )

    async with LifespanManager(off):
        pass

    assert not path.exists()

    on = create_app(settings(database_url=database_url, scheduler_enabled=True, sync_log_file=path))

    async with LifespanManager(on):
        pass

    assert "Scheduler started" in path.read_text()
    assert "Scheduler has been shut down" in path.read_text()


@pytest.mark.parametrize("on_startup", [True, False])
async def test_first_run_time(on_startup):
    scheduler = build_scheduler(settings(sync_on_startup=on_startup), noop)
    before = datetime.now(UTC)
    scheduler.start(paused=True)  # computes run times without running the job

    try:
        job = scheduler.get_job(SYNC_JOB_ID)
        if on_startup:
            assert before - timedelta(seconds=5) <= job.next_run_time <= datetime.now(UTC)
        else:
            assert job.next_run_time == job.trigger.get_next_fire_time(None, before) > before

        assert isinstance(job.trigger, CronTrigger) and job.max_instances == 1
    finally:
        scheduler.shutdown(wait=False)


def test_sync_on_startup_is_off_by_default(monkeypatch):
    assert settings().sync_on_startup is False

    monkeypatch.setenv("OLYMPIC_SYNC_ON_STARTUP", "true")

    assert settings().sync_on_startup is True


@pytest.mark.parametrize(
    ("scheduler_enabled", "on_startup", "runs"),
    [(True, True, 1), (True, False, 0), (False, True, 0)],
)
async def test_sync_runs_at_startup_only_when_enabled(
    monkeypatch, fetcher, database_url, tmp_path, scheduler_enabled, on_startup, runs
):
    started = asyncio.Event()

    async def fake_run_sync(*args):
        started.set()

    monkeypatch.setattr(scheduler_module, "run_sync", fake_run_sync)
    app = create_app(
        settings(
            database_url=database_url,
            scheduler_enabled=scheduler_enabled,
            sync_on_startup=on_startup,
            sync_log_file=tmp_path / "sync.log",
        )
    )

    async with LifespanManager(app):
        try:
            await asyncio.wait_for(started.wait(), timeout=2 if runs else 0.5)
        except TimeoutError:
            pass

        if app.state.scheduler is not None:
            assert app.state.scheduler.get_job(SYNC_JOB_ID).next_run_time > datetime.now(
                UTC
            )  # then on cron

    assert started.is_set() == bool(runs)
    assert fetcher.closed == runs
