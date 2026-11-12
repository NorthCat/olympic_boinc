from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class ChallengeType(StrEnum):
    PROJECT = "project"
    TEAM = "team"


def _pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Challenge(Base):
    __tablename__ = "challenge"

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_type: Mapped[ChallengeType] = mapped_column(_pg_enum(ChallengeType, "challenge_type"))
    name: Mapped[str] = mapped_column(Text)
    project_name: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    url: Mapped[str] = mapped_column(Text, unique=True)

    results: Mapped[list[ChallengeResult]] = relationship(
        back_populates="challenge",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChallengeResult.place",
    )


class Team(Base):
    __tablename__ = "team"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, unique=True)

    results: Mapped[list[ChallengeResult]] = relationship(back_populates="team")


class ChallengeResult(Base):
    __tablename__ = "challenge_result"
    __table_args__ = (
        UniqueConstraint("challenge_id", "team_id"),
        CheckConstraint("place BETWEEN 1 AND 3", name="place_range"),
        Index("ix_challenge_result_team_id_place", "team_id", "place"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenge.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("team.id"))
    place: Mapped[int] = mapped_column(SmallInteger)
    score: Mapped[Decimal | None] = mapped_column(Numeric)

    challenge: Mapped[Challenge] = relationship(back_populates="results")
    team: Mapped[Team] = relationship(back_populates="results")
