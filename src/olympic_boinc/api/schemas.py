"""Response models of the REST API."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from olympic_boinc.models import ChallengeType


class ChallengeTypeFilter(StrEnum):
    PROJECT = "project"
    TEAM = "team"
    ALL = "all"

    def to_type(self) -> ChallengeType | None:
        return None if self is ChallengeTypeFilter.ALL else ChallengeType(self.value)


class MedalRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    team_id: int
    team_name: str
    gold: int
    silver: int
    bronze: int
    total: int


class PlacementOut(BaseModel):
    team_id: int
    team_name: str
    place: int
    score: int | None


class ChallengeBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    challenge_type: ChallengeType
    name: str
    project_name: str | None
    start_at: datetime
    end_at: datetime
    url: str


class ChallengeOut(ChallengeBase):
    placements: list[PlacementOut]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int


class TeamChallengeOut(ChallengeBase):
    place: int


class TeamOut(BaseModel):
    id: int
    name: str
    gold: int
    silver: int
    bronze: int
    total: int
    challenges: list[TeamChallengeOut]


class HealthOut(BaseModel):
    status: str
