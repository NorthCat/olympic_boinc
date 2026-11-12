from datetime import UTC, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import AsyncMock

import pytest

from olympic_boinc.models import Challenge, ChallengeResult, ChallengeType, Team
from scripts.data_checks.check_scores import check_scores, find_issues, main


def result(place, score, name=None):
    return ChallengeResult(
        place=place,
        score=Decimal(score) if score is not None else None,
        team=Team(display_name=name or f"Team {place}"),
    )


@pytest.mark.parametrize(
    "scores,invalid",
    [
        (["30", "20", "10"], False),
        (["20", "30", "10"], True),
        (["30", "10", "20"], True),
        (["30", "30", "10"], True),
        (["30", "10", "10"], True),
        (["0.3", "0.2", "0.1"], False),
        (["100000000000000000002", "100000000000000000001", "100000000000000000000"], False),
    ],
)
def test_score_order(scores, invalid):
    assert bool(find_issues([result(i, score) for i, score in enumerate(scores, 1)])) == invalid


def test_all_teams_on_tied_places_are_checked():
    podium = [result(1, "100", "A"), result(1, "50", "B"), result(2, "60"), result(3, "10")]

    assert len(find_issues(podium)) == 1

    podium[1].score = Decimal("100")

    assert find_issues(podium) == []


def test_missing_places_and_unknown_scores():
    issues = find_issues([result(1, None), result(3, "NaN")])

    assert len(issues) == 3
    assert issues == [
        "No result for place 2: comparison is not possible.",
        "No valid score: Team 1, place 1.",
        "No valid score: Team 3, place 3.",
    ]


async def test_report_only_problematic_challenges():
    def challenge(id, scores):
        return Challenge(
            id=id,
            name=f"Challenge {id}",
            challenge_type=ChallengeType.PROJECT,
            end_at=datetime(2026, 1, 1, tzinfo=UTC),
            url=f"https://example.org/{id}",
            results=[result(i, score) for i, score in enumerate(scores, 1)],
        )

    session = AsyncMock()
    session.scalars.return_value = [
        challenge(1, ["30", "20", "10"]),
        challenge(2, ["10", "20", "30"]),
    ]
    output = StringIO()

    assert await check_scores(session, output) == 1

    report = output.getvalue()

    assert "Challenge 1" not in report

    for expected in [
        "Challenge 2",
        "https://example.org/2",
        "Team 1",
        "score: 10",
        "problematic: 1",
    ]:
        assert expected in report


async def test_empty_database():
    session = AsyncMock()
    session.scalars.return_value = []
    output = StringIO()

    assert await check_scores(session, output) == 0
    assert "Challenges checked: 0; problematic: 0" in output.getvalue()


def test_cli_help_is_in_english(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["check_scores.py", "--help"])

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 0
    assert "Validate podium scores: 1st place > 2nd place > 3rd place." in capsys.readouterr().out


def test_cli_error_is_in_english_without_connection_details(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["check_scores.py"])
    monkeypatch.setattr(
        "scripts.data_checks.check_scores.run",
        AsyncMock(side_effect=RuntimeError("postgresql://user:secret@db/private")),
    )

    assert main() == 2
    assert capsys.readouterr().err == (
        "Could not validate data (RuntimeError). Check the settings and database availability.\n"
    )
