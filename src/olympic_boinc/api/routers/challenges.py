from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from olympic_boinc import queries
from olympic_boinc.api.deps import SessionDep
from olympic_boinc.api.schemas import (
    ChallengeBase,
    ChallengeOut,
    ChallengeTypeFilter,
    Page,
    PlacementOut,
)
from olympic_boinc.models import Challenge

router = APIRouter(prefix="/api/challenges", tags=["challenges"])


def challenge_out(challenge: Challenge) -> ChallengeOut:
    placements = [
        PlacementOut(team_id=r.team_id, team_name=r.team.display_name, place=r.place, score=r.score)
        for r in challenge.results
    ]

    return ChallengeOut(
        **ChallengeBase.model_validate(challenge).model_dump(), placements=placements
    )


@router.get("", response_model=Page[ChallengeOut])
async def list_challenges(
    session: SessionDep,
    challenge_type: ChallengeTypeFilter = ChallengeTypeFilter.ALL,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[ChallengeOut]:
    """Challenges with their podium, latest end first."""
    challenges, total = await queries.list_challenges(session, challenge_type.to_type(), page, size)

    return Page[ChallengeOut](
        items=[challenge_out(c) for c in challenges], total=total, page=page, size=size
    )


@router.get("/years", response_model=list[int])
async def challenge_years(session: SessionDep) -> list[int]:
    """Distinct challenge end years in UTC, newest first, across both types."""
    return await queries.get_challenge_years(session)


@router.get("/{challenge_id}", response_model=ChallengeOut)
async def get_challenge(session: SessionDep, challenge_id: int) -> ChallengeOut:
    challenge = await queries.get_challenge(session, challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="Challenge not found")

    return challenge_out(challenge)
