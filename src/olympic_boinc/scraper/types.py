from dataclasses import dataclass
from datetime import datetime

from olympic_boinc.models import ChallengeType


class ParseError(Exception):
    """Unexpected page structure: BoincStats markup changed or the wrong page was returned."""


@dataclass(frozen=True)
class ChallengeSummary:
    challenge_type: ChallengeType
    name: str
    project_name: str | None
    start_at: datetime
    end_at: datetime
    url: str


@dataclass(frozen=True)
class TeamPlacement:
    team_name: str
    place: int
    score: int | None
