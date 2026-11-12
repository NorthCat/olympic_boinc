"""FastAPI application factory; run with `uvicorn olympic_boinc.api.app:create_app --factory`."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from olympic_boinc.api.routers import challenges, health, medals, teams
from olympic_boinc.apm import (
    APMMiddleware,
    close_client,
    create_client,
    instrument_database,
)
from olympic_boinc.config import Settings, get_settings
from olympic_boinc.db import create_engine, create_session_factory
from olympic_boinc.scheduler import (
    LOG_FORMAT,
    build_scheduler,
    close_sync_log,
    open_sync_log,
    sync_job,
)
from olympic_boinc.web import ASSETS
from olympic_boinc.web import router as web_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Sync results go to the log; a no-op when logging is already configured (e.g. by tests).
        logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

        engine = create_engine(settings.database_url)
        app.state.session_factory = create_session_factory(engine)
        app.state.scheduler = None

        app.state.apm_client = create_client(settings)
        instrument_database(engine, app.state.apm_client)

        sync_log = None
        if settings.scheduler_enabled:
            sync_log = open_sync_log(settings.sync_log_file)
            app.state.scheduler = build_scheduler(
                settings,
                partial(sync_job, app.state.session_factory, settings, app.state.apm_client),
            )
            app.state.scheduler.start()

        try:
            yield
        finally:
            if app.state.scheduler is not None:
                app.state.scheduler.shutdown(wait=False)
                # Let AsyncIOScheduler stop and log on the next loop iteration.
                await asyncio.sleep(0)
            if sync_log is not None:
                close_sync_log(sync_log)

            await engine.dispose()
            await close_client(app.state.apm_client)
            app.state.apm_client = None

    app = FastAPI(title="Olympic BOINC", lifespan=lifespan)

    for module in (medals, challenges, teams, health):
        app.include_router(module.router)

    app.include_router(web_router)
    app.mount("/static", StaticFiles(directory=ASSETS), name="static")
    app.add_middleware(APMMiddleware)

    return app
