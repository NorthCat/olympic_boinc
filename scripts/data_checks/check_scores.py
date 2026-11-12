"""Report stored challenges whose podium scores do not strictly decrease."""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import TextIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from olympic_boinc.config import get_settings
from olympic_boinc.db import create_engine, create_session_factory
from olympic_boinc.models import Challenge, ChallengeResult


def find_issues(results: Sequence[ChallengeResult]) -> list[str]:
    issues = []

    for place in (1, 2, 3):
        if not any(result.place == place for result in results):
            issues.append(f"No result for place {place}: comparison is not possible.")

    for result in results:
        if result.score is None or not result.score.is_finite():
            issues.append(f"No valid score: {result.team.display_name}, place {result.place}.")

    for higher, lower in ((1, 2), (2, 3)):
        higher_scores = [
            r.score
            for r in results
            if r.place == higher and r.score is not None and r.score.is_finite()
        ]
        lower_scores = [
            r.score
            for r in results
            if r.place == lower and r.score is not None and r.score.is_finite()
        ]
        if higher_scores and lower_scores and min(higher_scores) <= max(lower_scores):
            issues.append(
                f"Invalid order: the score for place {higher} "
                f"must be strictly greater than the score for place {lower}."
            )

    return issues


async def check_scores(session: AsyncSession, output: TextIO) -> int:
    challenges = await session.scalars(
        select(Challenge)
        .options(selectinload(Challenge.results).selectinload(ChallengeResult.team))
        .order_by(Challenge.end_at, Challenge.id)
    )
    checked = problematic = 0

    for challenge in challenges:
        checked += 1
        issues = find_issues(challenge.results)
        if not issues:
            continue
        problematic += 1
        print(f"\nChallenge #{challenge.id}: {challenge.name}", file=output)
        print(
            f"Type: {challenge.challenge_type.value}; end: {challenge.end_at.isoformat()}",
            file=output,
        )
        print(challenge.url, file=output)

        for issue in issues:
            print(f"  ! {issue}", file=output)

        for result in sorted(challenge.results, key=lambda r: (r.place, r.team.display_name)):
            score = format(result.score, "f") if result.score is not None else "unknown"
            print(
                f"  Place {result.place}: {result.team.display_name}; score: {score}", file=output
            )

    print(f"\nChallenges checked: {checked}; problematic: {problematic}.", file=output)

    return problematic


async def run() -> int:
    engine = create_engine(get_settings().database_url)

    try:
        async with create_session_factory(engine)() as session:
            return 1 if await check_scores(session, sys.stdout) else 0
    finally:
        await engine.dispose()


def main() -> int:
    argparse.ArgumentParser(
        description="Validate podium scores: 1st place > 2nd place > 3rd place."
    ).parse_args()

    try:
        return asyncio.run(run())
    except Exception as exc:
        # Connection errors may contain a DSN; do not print credentials or raw exceptions.
        print(
            f"Could not validate data ({type(exc).__name__}). "
            "Check the settings and database availability.",
            file=sys.stderr,
        )

        return 2


if __name__ == "__main__":
    raise SystemExit(main())
