from fastapi import APIRouter, HTTPException

from olympic_boinc import queries
from olympic_boinc.api.deps import SessionDep
from olympic_boinc.api.schemas import ChallengeBase, TeamChallengeOut, TeamOut

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(session: SessionDep, team_id: int) -> TeamOut:
    """The team's medals and the challenges where it placed, latest first."""
    card = await queries.get_team_card(session, team_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Team not found")

    return TeamOut(
        id=card.team.id,
        name=card.team.display_name,
        gold=card.medals.gold,
        silver=card.medals.silver,
        bronze=card.medals.bronze,
        total=card.medals.total,
        challenges=[
            TeamChallengeOut(
                **ChallengeBase.model_validate(r.challenge).model_dump(), place=r.place
            )
            for r in card.results
        ],
    )
