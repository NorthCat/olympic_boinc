"""Export of stored challenges with their podiums to a flat CSV file and import of such a file.

Usage:
    python -m olympic_boinc.csv_transfer export [FILE]
    python -m olympic_boinc.csv_transfer import FILE

One row per podium place, no database ids. Import adds only challenges whose URL is not stored yet;
the whole file is checked first and nothing is written if it has errors.
"""

import argparse
import asyncio
import csv
import io
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from olympic_boinc.config import get_settings
from olympic_boinc.db import create_engine, create_session_factory
from olympic_boinc.models import Challenge, ChallengeResult, ChallengeType, Team
from olympic_boinc.scraper.types import ChallengeSummary, TeamPlacement
from olympic_boinc.sync import save_challenge

DEFAULT_EXPORT_DIR = Path("dumps")  # relative to the working directory
COLUMNS = [
    "challenge_type",
    "challenge_name",
    "project_name",
    "start_at",
    "end_at",
    "url",
    "team",
    "place",
    "score",
]


class CsvImportError(Exception):
    """The file has errors; `errors` lists them as "line N: reason" (the header is line 1)."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


async def export_csv(session_factory: async_sessionmaker[AsyncSession], path: Path) -> int:
    """Write podium places to `path`, creating its directory; return the row count."""
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Challenge, ChallengeResult.place, ChallengeResult.score, Team.display_name)
                .join(ChallengeResult, ChallengeResult.challenge_id == Challenge.id)
                .join(Team, Team.id == ChallengeResult.team_id)
                # "C" collation: the same order on any server, whatever its locale.
                .order_by(
                    Challenge.end_at,
                    Challenge.url,
                    ChallengeResult.place,
                    Team.display_name.collate("C"),
                )
            )
        ).all()

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(COLUMNS)

        for challenge, place, score, team in rows:
            writer.writerow(
                [
                    challenge.challenge_type.value,
                    challenge.name,
                    challenge.project_name or "",
                    challenge.start_at.astimezone(UTC).isoformat(),
                    challenge.end_at.astimezone(UTC).isoformat(),
                    challenge.url,
                    team,
                    place,
                    "" if score is None else int(score),
                ]
            )

    return len(rows)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _parse_row(row: dict[str | None, str | None]) -> tuple[ChallengeSummary, TeamPlacement]:
    """One data row; ValueError with the reason on bad values."""
    if row.get(None):
        raise ValueError("more values than columns")

    values = {column: row.get(column) or "" for column in COLUMNS}

    for column in ("challenge_name", "url", "team"):
        if not values[column]:
            raise ValueError(f"{column} is empty")

    try:
        challenge_type = ChallengeType(values["challenge_type"])
    except ValueError:
        raise ValueError(f"unknown challenge_type {values['challenge_type']!r}") from None

    dates = {}

    for column in ("start_at", "end_at"):
        try:
            dates[column] = _parse_datetime(values[column])
        except ValueError:
            raise ValueError(f"invalid {column} {values[column]!r}") from None

    try:
        place = int(values["place"])
    except ValueError:
        place = 0

    if not 1 <= place <= 3:
        raise ValueError(f"place must be 1..3, got {values['place']!r}")

    score = None
    if values["score"]:
        try:
            score = int(values["score"])
        except ValueError:
            score = -1

        if score < 0:
            raise ValueError(f"score must be a non-negative integer, got {values['score']!r}")

    summary = ChallengeSummary(
        challenge_type=challenge_type,
        name=values["challenge_name"],
        project_name=values["project_name"] or None,
        start_at=dates["start_at"],
        end_at=dates["end_at"],
        url=values["url"],
    )

    return summary, TeamPlacement(team_name=values["team"], place=place, score=score)


def parse_csv(path: Path) -> list[tuple[ChallengeSummary, list[TeamPlacement]]]:
    """Read podiums in file order; raise CsvImportError containing all validation errors."""
    errors: list[str] = []
    challenges: dict[
        str, tuple[int, ChallengeSummary, list[TeamPlacement]]
    ] = {}  # url -> first line, ...
    team_lines: dict[tuple[str, str], int] = {}  # (url, team) -> line

    try:
        # utf-8-sig: spreadsheet editors often save UTF-8 with a BOM.
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError([f"file is not UTF-8: {exc}"]) from None

    reader = csv.DictReader(io.StringIO(text, newline=""))

    try:
        header = reader.fieldnames or []
        missing = [column for column in COLUMNS if column not in header]
        extra = [column for column in header if column not in COLUMNS]
        if missing or extra or len(header) != len(set(header)):
            raise CsvImportError(
                [
                    f"line 1: header must be {','.join(COLUMNS)}; "
                    f"missing: {missing or '-'}, unexpected: {extra or '-'}"
                ]
            )

        rows = list(enumerate(reader, start=2))
    except csv.Error as exc:
        raise CsvImportError([f"line {reader.line_num}: malformed CSV: {exc}"]) from None

    for line, row in rows:
        try:
            summary, placement = _parse_row(row)
        except ValueError as exc:
            errors.append(f"line {line}: {exc}")
            continue

        if summary.url not in challenges:
            challenges[summary.url] = (line, summary, [])
        first_line, first_summary, placements = challenges[summary.url]
        if summary != first_summary:
            errors.append(
                f"line {line}: challenge fields differ from line {first_line} with the same url"
            )
            continue
        if (seen := team_lines.get((summary.url, placement.team_name))) is not None:
            errors.append(
                f"line {line}: team {placement.team_name!r} "
                f"is already listed for this challenge on line {seen}"
            )
            continue
        team_lines[summary.url, placement.team_name] = line
        placements.append(placement)

    if errors:
        raise CsvImportError(errors)

    return [(summary, placements) for _, summary, placements in challenges.values()]


async def import_csv(
    session_factory: async_sessionmaker[AsyncSession], path: Path
) -> tuple[int, int]:
    """Import unstored challenges in one transaction; return (added, skipped)."""
    challenges = parse_csv(path)
    added = 0

    async with session_factory() as session, session.begin():
        for summary, placements in challenges:
            added += await save_challenge(session, summary, placements)

    return added, len(challenges) - added


async def run(argv: list[str]) -> int:
    """The command line; returns the exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m olympic_boinc.csv_transfer", description=__doc__.splitlines()[0]
    )
    parser.add_argument("command", choices=["export", "import"])
    parser.add_argument(
        "file",
        type=Path,
        nargs="?",
        help=f"required for import; export defaults to {DEFAULT_EXPORT_DIR}/",
    )
    args = parser.parse_args(argv)
    if args.file is None:
        if args.command == "import":
            parser.error("import needs a FILE")
        args.file = DEFAULT_EXPORT_DIR / f"olympic_boinc_{datetime.now(UTC):%Y%m%d_%H%M%S}.csv"

    engine = create_engine(get_settings().database_url)

    try:
        session_factory = create_session_factory(engine)
        if args.command == "export":
            print(f"exported {await export_csv(session_factory, args.file)} rows -> {args.file}")
        else:
            added, skipped = await import_csv(session_factory, args.file)
            print(f"imported {args.file}: added {added}, skipped {skipped} (already stored)")
    except CsvImportError as exc:
        print(f"{args.file}: {len(exc.errors)} error(s), nothing imported", file=sys.stderr)
        print(exc, file=sys.stderr)

        return 1
    except OSError as exc:
        print(exc, file=sys.stderr)

        return 1
    finally:
        await engine.dispose()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run(sys.argv[1:])))
