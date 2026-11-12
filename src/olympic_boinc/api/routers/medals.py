from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from olympic_boinc import queries
from olympic_boinc.api.deps import SessionDep
from olympic_boinc.api.schemas import ChallengeTypeFilter, MedalRow

router = APIRouter(prefix="/api/medals", tags=["medals"])


@router.get("", response_model=list[MedalRow])
async def medal_table(
    session: SessionDep,
    challenge_type: ChallengeTypeFilter = ChallengeTypeFilter.ALL,
    date_from: Annotated[
        date | None, Query(alias="from", description="Challenges ending on or after this day (UTC)")
    ] = None,
    date_to: Annotated[
        date | None, Query(alias="to", description="Challenges ending on or before this day (UTC)")
    ] = None,
) -> list[MedalRow]:
    """Olympic medal table: gold, then silver, then bronze (descending), then team name."""
    rows = await queries.get_medal_table(session, challenge_type.to_type(), date_from, date_to)

    return [MedalRow.model_validate(row) for row in rows]
