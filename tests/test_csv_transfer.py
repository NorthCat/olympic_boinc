import csv
import re
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select, update

from olympic_boinc import csv_transfer
from olympic_boinc.config import Settings
from olympic_boinc.csv_transfer import (
    COLUMNS,
    CsvImportError,
    export_csv,
    import_csv,
    parse_csv,
    run,
)
from olympic_boinc.models import Challenge, ChallengeResult, ChallengeType, Team
from tests.factories import add_challenge, seed

URL = "https://www.boincstats.com/stats/pchallenge/team/list/1/rank"
ROW = {
    "challenge_type": "project",
    "challenge_name": "Sprint",
    "project_name": "PrimeGrid",
    "start_at": "2025-01-01T00:00:00+00:00",
    "end_at": "2025-01-08T00:00:00+00:00",
    "url": URL,
    "team": "Alpha",
    "place": "1",
    "score": "100",
}


def write_csv(path, rows: list[dict], header: list[str] = COLUMNS):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    return path


def read_rows(path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def podium(url: str = URL, **changes) -> list[dict]:
    """Rows of one challenge: Alpha 1st, Bravo 2nd, Charlie 3rd."""
    return [
        {**ROW, "url": url, "team": t, "place": str(p), **changes}
        for t, p in [("Alpha", 1), ("Bravo", 2), ("Charlie", 3)]
    ]


async def count(session_factory, model) -> int:
    async with session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def test_export_empty_db_writes_header_only(session_factory, tmp_path):
    assert await export_csv(session_factory, tmp_path / "out.csv") == 0
    assert read_rows(tmp_path / "out.csv") == [COLUMNS]


async def test_export_rows_in_stable_order(session_factory, tmp_path):
    async with session_factory() as session:
        await seed(session)
        await session.execute(
            update(ChallengeResult).where(ChallengeResult.place == 3).values(score=None)
        )
        await session.commit()

    assert await export_csv(session_factory, tmp_path / "out.csv") == 11

    header, *rows = read_rows(tmp_path / "out.csv")

    assert header == COLUMNS
    assert rows[0] == [
        "project", "c1", "PrimeGrid", "2024-03-01T12:00:00+00:00", "2025-03-01T12:00:00+00:00",
        "https://www.boincstats.com/test/c1", "Alpha", "1", "1000",
    ]  # fmt: skip
    # By end date (c1, c3, c2, c4), then place, then team name (shared 2nd place in c2).
    assert [(r[1], r[6], r[7]) for r in rows] == [
        ("c1", "Alpha", "1"), ("c1", "Bravo", "2"), ("c1", "Charlie", "3"),
        ("c3", "Bravo", "1"), ("c3", "Charlie", "2"), ("c3", "Alpha", "3"),
        ("c2", "Alpha", "1"), ("c2", "Bravo", "2"), ("c2", "Delta", "2"),
        ("c4", "Echo", "1"), ("c4", "Aardvark", "2"),
    ]  # fmt: skip

    team_challenge = next(r for r in rows if r[1] == "c3")

    assert team_challenge[2] == ""  # no project name
    assert {r[8] for r in rows if r[7] == "3"} == {""}  # no score


def test_parse_groups_rows_by_challenge(tmp_path):
    rows = podium() + podium(
        "https://www.boincstats.com/stats/challenge/team/list/2/rank",
        challenge_type="team",
        project_name="",
    )
    challenges = parse_csv(write_csv(tmp_path / "in.csv", rows))

    assert [(s.challenge_type, s.project_name, len(p)) for s, p in challenges] == [
        (ChallengeType.PROJECT, "PrimeGrid", 3),
        (ChallengeType.TEAM, None, 3),
    ]

    summary, placements = challenges[0]

    assert summary.end_at == datetime(2025, 1, 8, tzinfo=UTC)
    assert [(p.team_name, p.place, p.score) for p in placements] == [
        ("Alpha", 1, 100),
        ("Bravo", 2, 100),
        ("Charlie", 3, 100),
    ]


def test_parse_date_without_zone_is_utc_and_other_zones_are_converted(tmp_path):
    rows = [
        {
            **ROW,
            "start_at": "2025-01-01T03:00:00+03:00",
            "end_at": "2025-01-08 00:00:00",
            "score": "",
        }
    ]
    [(summary, [placement])] = parse_csv(write_csv(tmp_path / "in.csv", rows))

    assert summary.start_at == datetime(2025, 1, 1, tzinfo=UTC)
    assert summary.end_at == datetime(2025, 1, 8, tzinfo=UTC)
    assert placement.score is None


def test_parse_accepts_utf8_bom(tmp_path):
    path = write_csv(tmp_path / "in.csv", podium())
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())

    assert len(parse_csv(path)) == 1


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"challenge_type": "solo"}, "unknown challenge_type"),
        ({"challenge_name": ""}, "challenge_name is empty"),
        ({"url": ""}, "url is empty"),
        ({"team": ""}, "team is empty"),
        ({"start_at": "01.01.2025"}, "invalid start_at"),
        ({"end_at": ""}, "invalid end_at"),
        ({"place": "4"}, "place must be 1..3"),
        ({"place": "0"}, "place must be 1..3"),
        ({"place": "first"}, "place must be 1..3"),
        ({"score": "-5"}, "score must be a non-negative integer"),
        ({"score": "1.5"}, "score must be a non-negative integer"),
        ({"end_at": "2025-01-09T00:00:00+00:00"}, "challenge fields differ from line 2"),
        ({"team": "Alpha"}, "team 'Alpha' is already listed for this challenge on line 2"),
    ],
)
def test_parse_rejects_bad_row(tmp_path, change, reason):
    rows = podium()
    rows[1] = {**rows[1], **change}

    with pytest.raises(CsvImportError) as exc:
        parse_csv(write_csv(tmp_path / "in.csv", rows))

    assert len(exc.value.errors) == 1
    assert exc.value.errors[0].startswith("line 3: ")
    assert reason in exc.value.errors[0]


def test_parse_reports_all_errors_with_line_numbers(tmp_path):
    rows = podium() + podium("https://www.boincstats.com/x")
    rows[0] = {**rows[0], "place": "7"}
    rows[4] = {**rows[4], "score": "many"}

    with pytest.raises(CsvImportError) as exc:
        parse_csv(write_csv(tmp_path / "in.csv", rows))

    assert [e.split(":")[0] for e in exc.value.errors] == ["line 2", "line 6"]


@pytest.mark.parametrize(
    "header",
    [COLUMNS[:-1], [*COLUMNS, "comment"], [c.replace("team", "team_name") for c in COLUMNS]],
    ids=["missing", "extra", "renamed"],
)
def test_parse_rejects_bad_header(tmp_path, header):
    with pytest.raises(CsvImportError) as exc:
        parse_csv(write_csv(tmp_path / "in.csv", podium(), header))

    assert exc.value.errors[0].startswith("line 1: header must be")


def test_parse_rejects_extra_values_and_non_utf8(tmp_path):
    path = tmp_path / "in.csv"
    path.write_text(
        ",".join(COLUMNS) + "\n" + ",".join(ROW.values()) + ",extra\n", encoding="utf-8"
    )

    with pytest.raises(CsvImportError, match="line 2: more values than columns"):
        parse_csv(path)

    path.write_bytes(
        (",".join(COLUMNS) + "\n" + ",".join(ROW.values()) + "\n")
        .replace("Alpha", "Альфа")
        .encode("cp1251")
    )

    with pytest.raises(CsvImportError, match="not UTF-8"):
        parse_csv(path)


async def test_import_adds_challenges_teams_and_results(session_factory, tmp_path):
    path = write_csv(
        tmp_path / "in.csv", podium() + podium("https://www.boincstats.com/x", score="")
    )

    assert await import_csv(session_factory, path) == (2, 0)
    assert (await count(session_factory, Challenge), await count(session_factory, Team)) == (2, 3)
    assert await count(session_factory, ChallengeResult) == 6


async def test_repeated_import_skips_everything(session_factory, tmp_path):
    path = write_csv(tmp_path / "in.csv", podium() + podium("https://www.boincstats.com/x"))
    await import_csv(session_factory, path)

    assert await import_csv(session_factory, path) == (0, 2)
    assert (
        await count(session_factory, Challenge),
        await count(session_factory, ChallengeResult),
    ) == (2, 6)


async def test_import_skips_stored_challenges_without_changing_them(session_factory, tmp_path):
    async with session_factory() as session:
        stored = await add_challenge(
            session, "c1", ChallengeType.PROJECT, datetime(2025, 3, 1, tzinfo=UTC), [("Alpha", 2)]
        )
        await session.commit()

    # The file has the stored challenge with a different podium and name, plus a new one.
    path = write_csv(tmp_path / "in.csv", podium(stored.url, challenge_name="renamed") + podium())

    assert await import_csv(session_factory, path) == (1, 1)

    async with session_factory() as session:
        assert await session.scalar(select(Challenge.name).where(Challenge.id == stored.id)) == "c1"

        results = (
            await session.execute(
                select(Team.display_name, ChallengeResult.place)
                .join(Team)
                .where(ChallengeResult.challenge_id == stored.id)
            )
        ).all()

        assert results == [("Alpha", 2)]


async def test_import_links_results_to_existing_team(session_factory, tmp_path):
    async with session_factory() as session:
        await add_challenge(
            session, "c1", ChallengeType.PROJECT, datetime(2025, 3, 1, tzinfo=UTC), [("Alpha", 1)]
        )
        await session.commit()
        alpha_id = await session.scalar(select(Team.id).where(Team.display_name == "Alpha"))

    await import_csv(session_factory, write_csv(tmp_path / "in.csv", podium()))

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).where(Team.display_name == "Alpha")) == 1
        assert (
            await session.scalar(select(func.count()).where(ChallengeResult.team_id == alpha_id))
            == 2
        )


async def test_import_with_errors_changes_nothing(session_factory, tmp_path):
    rows = podium() + podium("https://www.boincstats.com/x")
    rows[-1] = {**rows[-1], "place": "4"}

    with pytest.raises(CsvImportError):
        await import_csv(session_factory, write_csv(tmp_path / "in.csv", rows))

    assert (await count(session_factory, Challenge), await count(session_factory, Team)) == (0, 0)


async def test_round_trip(session_factory, tmp_path):
    async with session_factory() as session:
        await seed(session)
        await add_challenge(
            session, "tricky", ChallengeType.TEAM, datetime(2026, 2, 1, tzinfo=UTC),
            [('Team "Quoted", Inc.', 1), ("Россия", 2), ("  spaced  ", 3)],
        )  # fmt: skip
        await session.commit()

    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    await export_csv(session_factory, first)

    async with session_factory() as session:
        for model in (ChallengeResult, Challenge, Team):
            await session.execute(delete(model))

        await session.commit()

    assert await import_csv(session_factory, first) == (5, 0)

    await export_csv(session_factory, second)

    assert second.read_bytes() == first.read_bytes()
    assert {r[6] for r in read_rows(second)} >= {'Team "Quoted", Inc.', "Россия", "  spaced  "}


@pytest.fixture
def cli_db(monkeypatch, database_url, session_factory):
    """The CLI works on the test database, inside the test's rolled-back transaction."""
    monkeypatch.setattr(
        csv_transfer, "get_settings", lambda: Settings(_env_file=None, database_url=database_url)
    )
    monkeypatch.setattr(csv_transfer, "create_session_factory", lambda engine: session_factory)

    return session_factory


async def test_cli_import_and_export(cli_db, tmp_path, capsys):
    path = write_csv(tmp_path / "in.csv", podium() + podium("https://www.boincstats.com/x"))

    assert await run(["import", str(path)]) == 0
    assert "added 2, skipped 0" in capsys.readouterr().out

    assert await run(["export", str(tmp_path / "out.csv")]) == 0
    assert "exported 6 rows" in capsys.readouterr().out
    assert len(read_rows(tmp_path / "out.csv")) == 7


async def test_cli_export_without_file_goes_to_dumps(cli_db, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert await run(["export"]) == 0

    [path] = (tmp_path / "dumps").iterdir()

    assert re.fullmatch(r"olympic_boinc_\d{8}_\d{6}\.csv", path.name)
    assert read_rows(path) == [COLUMNS]
    assert f"-> dumps/{path.name}" in capsys.readouterr().out


async def test_cli_import_needs_file(cli_db):
    with pytest.raises(SystemExit) as exc:
        await run(["import"])

    assert exc.value.code == 2


async def test_cli_import_with_errors_exits_with_1(cli_db, tmp_path, capsys):
    rows = podium()
    rows[0] = {**rows[0], "place": "9"}

    assert await run(["import", str(write_csv(tmp_path / "in.csv", rows))]) == 1

    err = capsys.readouterr().err

    assert "1 error(s), nothing imported" in err
    assert "line 2: place must be 1..3" in err
    assert await count(cli_db, Challenge) == 0


async def test_cli_missing_file_exits_with_1(cli_db, tmp_path):
    assert await run(["import", str(tmp_path / "nope.csv")]) == 1
