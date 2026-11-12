import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from olympic_boinc.api.deps import SessionDep
from olympic_boinc.api.schemas import HealthOut

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut, responses={503: {"model": HealthOut}})
async def health(session: SessionDep, response: Response) -> HealthOut:
    """200 when the database answers, 503 otherwise."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.warning("health check: database unavailable", exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return HealthOut(status="unavailable")

    return HealthOut(status="ok")
