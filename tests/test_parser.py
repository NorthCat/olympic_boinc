from datetime import UTC, datetime
from pathlib import Path

import pytest

from olympic_boinc.models import ChallengeType
from olympic_boinc.scraper.parser import parse_challenge, parse_overview
from olympic_boinc.scraper.types import ChallengeSummary, ParseError, TeamPlacement

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = "https://www.boincstats.com"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def replace_once(html: str, old: str, new: str) -> str:
    """Build a synthetic fixture, requiring exactly one occurrence of the edited fragment."""
    assert html.count(old) == 1, old

    return html.replace(old, new)


# --- overview ---


def test_project_overview_returns_only_completed():
    challenges = parse_overview(
        fixture("pchallenge_overview.html"), ChallengeType.PROJECT, BASE_URL
    )

    assert len(challenges) == 205  # 208 rows, 3 of them Upcoming
    assert {c.challenge_type for c in challenges} == {ChallengeType.PROJECT}
    assert challenges[0] == ChallengeSummary(
        challenge_type=ChallengeType.PROJECT,
        name="'Baengno Challenge",
        project_name="PrimeGrid",
        start_at=datetime(2026, 9, 7, 14, 41, tzinfo=UTC),
        end_at=datetime(2026, 9, 12, 14, 41, tzinfo=UTC),
        url="https://www.boincstats.com/stats/pchallenge/team/list/42108/rank",
    )


def test_team_overview_returns_only_completed():
    challenges = parse_overview(fixture("challenge_overview.html"), ChallengeType.TEAM, BASE_URL)

    assert len(challenges) == 861  # the ad row without <td> is skipped
    assert {c.challenge_type for c in challenges} == {ChallengeType.TEAM}
    assert challenges[0] == ChallengeSummary(
        challenge_type=ChallengeType.TEAM,
        name="SiDock comes back. Research against ebola",
        project_name="SiDock@home",
        start_at=datetime(2026, 9, 16, 20, 15, tzinfo=UTC),
        end_at=datetime(2026, 9, 23, 20, 15, tzinfo=UTC),
        url="https://www.boincstats.com/stats/challenge/team/list/1135/rank",
    )


def test_upcoming_challenges_are_skipped():
    names = {
        c.name
        for c in parse_overview(
            fixture("pchallenge_overview.html"), ChallengeType.PROJECT, BASE_URL
        )
    }

    assert not names & {
        "Photon Challenge",
        "Lehmer's Birthday Challenge",
        "Suzuki's Birthday Challenge",
    }


def test_challenges_with_the_same_name_get_different_urls():
    challenges = parse_overview(
        fixture("pchallenge_overview.html"), ChallengeType.PROJECT, BASE_URL
    )

    urls = {c.url for c in challenges if c.name == "The Drive for Five"}

    assert urls == {
        "https://www.boincstats.com/stats/pchallenge/team/list/1/rank",
        "https://www.boincstats.com/stats/pchallenge/team/list/332/rank",
    }


@pytest.mark.parametrize(
    ("name", "challenge_type"),
    [
        ("pchallenge_overview.html", ChallengeType.PROJECT),
        ("challenge_overview.html", ChallengeType.TEAM),
    ],
)
def test_overview_urls_are_unique_and_dates_are_utc(name, challenge_type):
    challenges = parse_overview(fixture(name), challenge_type, BASE_URL)

    assert len({c.url for c in challenges}) == len(challenges)

    for c in challenges:
        assert c.start_at.tzinfo is UTC and c.end_at.tzinfo is UTC


def test_overview_dates_match_the_page():
    challenges = parse_overview(fixture("challenge_overview.html"), ChallengeType.TEAM, BASE_URL)

    by_url = {c.url.rsplit("/", 2)[-2]: c for c in challenges}

    assert (by_url["1134"].start_at, by_url["1134"].end_at) == (
        datetime(2026, 4, 23, 20, 15, tzinfo=UTC),
        datetime(2026, 4, 30, 20, 15, tzinfo=UTC),
    )
    assert (by_url["1133"].start_at, by_url["1133"].end_at) == (
        datetime(2026, 2, 21, 21, 45, tzinfo=UTC),
        datetime(2026, 2, 28, 21, 45, tzinfo=UTC),
    )


def test_end_before_start_is_returned_as_on_the_page():
    challenges = parse_overview(
        fixture("pchallenge_overview.html"), ChallengeType.PROJECT, BASE_URL
    )

    by_url = {c.url.rsplit("/", 2)[-2]: c for c in challenges}

    assert (by_url["28795"].start_at, by_url["28795"].end_at) == (
        datetime(2023, 3, 8, 15, 0, tzinfo=UTC),
        datetime(1970, 1, 1, 0, 0, tzinfo=UTC),
    )
    assert (by_url["138"].start_at, by_url["138"].end_at) == (
        datetime(2015, 6, 12, 18, 0, tzinfo=UTC),
        datetime(2015, 4, 15, 18, 0, tzinfo=UTC),
    )


# --- challenge results ---


def test_team_challenge_place_comes_from_rank_column():
    assert parse_challenge(fixture("challenge_results.html")) == [
        TeamPlacement("BOINCstats", 1, 807_386),
        TeamPlacement("SETI.Germany", 2, 372_206),
        TeamPlacement("Rechenkraft.net", 3, 279_365),
    ]


def test_project_challenge_place_comes_from_credit():
    # The header row after <tbody> wrongly labels the second column "Rank"; it must be ignored.
    assert parse_challenge(fixture("pchallenge_results.html")) == [
        TeamPlacement("The FPS Team", 1, 119_944_472),
        TeamPlacement("Czech National Team", 2, 95_487_504),
        TeamPlacement("BOINC@AUSTRALIA", 3, 82_121_224),
    ]


def test_challenge_without_results_gives_empty_list():
    assert parse_challenge(fixture("challenge_no_results.html")) == []


def with_ranks(*ranks: int) -> str:
    """challenge_results.html with the Rank column of the first rows replaced by `ranks`."""
    html = fixture("challenge_results.html")

    for row, rank in enumerate(ranks, start=1):
        html = replace_once(
            html, f'<a name="{row}"></a>{row}</td>', f'<a name="{row}"></a>{rank}</td>'
        )

    return html


@pytest.mark.parametrize(
    ("ranks", "expected"),
    [
        ((1, 1, 3), [1, 1, 3]),
        ((1, 2, 2), [1, 2, 2]),
        ((1, 2, 3, 3), [1, 2, 3, 3]),
    ],
)
def test_ties_in_rank_column(ranks, expected):
    placements = parse_challenge(with_ranks(*ranks))

    assert [p.place for p in placements] == expected
    assert [p.team_name for p in placements][:3] == [
        "BOINCstats",
        "SETI.Germany",
        "Rechenkraft.net",
    ]


def test_equal_credit_gives_the_same_place():
    html = fixture("pchallenge_results.html").replace("95,487,504", "119,944,472")

    assert parse_challenge(html) == [
        TeamPlacement("The FPS Team", 1, 119_944_472),
        TeamPlacement("Czech National Team", 1, 119_944_472),
        TeamPlacement("BOINC@AUSTRALIA", 3, 82_121_224),
    ]


# --- errors ---


def test_overview_without_table_raises():
    html = fixture("pchallenge_overview.html").replace('id="tblChallenges"', 'id="other"')

    with pytest.raises(ParseError, match="table#tblChallenges"):
        parse_overview(html, ChallengeType.PROJECT, BASE_URL)


def test_overview_without_required_column_raises():
    html = replace_once(fixture("challenge_overview.html"), ">Status</div>", ">State</div>")

    with pytest.raises(ParseError, match="Status"):
        parse_overview(html, ChallengeType.TEAM, BASE_URL)


def test_completed_challenge_without_id_raises():
    html = replace_once(
        fixture("challenge_overview.html"), 'onclick="challengeChatShow(1135);"', ""
    )

    with pytest.raises(ParseError, match="challenge ID"):
        parse_overview(html, ChallengeType.TEAM, BASE_URL)


def test_results_without_required_column_raises():
    html = fixture("challenge_results.html").replace("Totalcredit", "Credit")

    with pytest.raises(ParseError, match="Total credit"):
        parse_challenge(html)


@pytest.mark.parametrize(
    "name", ["cloudflare_challenge.html", "captcha_challenge.html", "pchallenge_overview.html"]
)
def test_other_page_instead_of_results_raises(name):
    with pytest.raises(ParseError, match="table#tblStats"):
        parse_challenge(fixture(name))


def test_home_page_instead_of_results_raises():
    # BoincStats answers an unknown URL with 200 and its home page.
    html = (
        "<html><head><title>Home | BOINCstats/BAM!</title></head>"
        "<body><table><tr><td>x</td></tr></table></body></html>"
    )

    with pytest.raises(ParseError, match="table#tblStats"):
        parse_challenge(html)


@pytest.mark.parametrize("name", ["cloudflare_challenge.html", "captcha_challenge.html"])
def test_blocked_page_instead_of_overview_raises(name):
    with pytest.raises(ParseError, match="table#tblChallenges"):
        parse_overview(fixture(name), ChallengeType.PROJECT, BASE_URL)
