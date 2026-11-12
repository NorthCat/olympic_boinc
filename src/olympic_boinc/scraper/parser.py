"""Parse BoincStats pages into challenge summaries and podiums; pure functions, no I/O."""

import re
from datetime import UTC, datetime
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser, LexborNode

from olympic_boinc.models import ChallengeType
from olympic_boinc.scraper.types import ChallengeSummary, ParseError, TeamPlacement

PODIUM_PLACES = 3
DATE_FORMAT = "%Y-%m-%d %H:%M"
URL_SEGMENTS = {ChallengeType.PROJECT: "pchallenge", ChallengeType.TEAM: "challenge"}
PROJECT_ID_RE = re.compile(r"/stats/pchallenge/team/list/(\d+)/")
TEAM_ID_RE = re.compile(r"challengeChatShow\((\d+)\)")


def _find(node: LexborHTMLParser | LexborNode, selector: str) -> LexborNode:
    found = node.css_first(selector)
    if found is None:
        raise ParseError(f"element not found: {selector}")

    return found


def _header_key(text: str) -> str:
    """Headers are compared ignoring whitespace and case: they contain `&nbsp;` and `<br>`."""
    return "".join(text.split()).lower()


def _columns(table: LexborNode, selector: str, required: tuple[str, ...]) -> dict[str, int]:
    """Maps header keys to cell indexes, taken from the first header row of the table.

    `colspan` is taken into account; a repeated header keeps its first column. After floatThead
    has run, the header cells in the table are empty and the text is left only in `aria-label`.
    """
    columns: dict[str, int] = {}
    index = 0

    for th in _find(table, "thead tr").css("th"):
        columns.setdefault(_header_key(th.text() or th.attributes.get("aria-label") or ""), index)
        index += int(th.attributes.get("colspan") or 1)

    missing = [name for name in required if _header_key(name) not in columns]
    if missing:
        raise ParseError(f"{selector}: columns not found: {', '.join(missing)}")

    return columns


def _cell(cells: list[LexborNode], columns: dict[str, int], name: str) -> str:
    index = columns[_header_key(name)]
    if index >= len(cells):
        raise ParseError(f"row has no cell for column {name!r}")

    return cells[index].text().strip()


def _parse_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, DATE_FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise ParseError(f"unexpected date format: {value!r}") from exc


def _parse_int(value: str, what: str) -> int:
    try:
        return int(value.replace(",", ""))
    except ValueError as exc:
        raise ParseError(f"unexpected {what}: {value!r}") from exc


def _challenge_id(row: LexborNode, challenge_type: ChallengeType) -> str:
    if challenge_type is ChallengeType.PROJECT:
        matches = (PROJECT_ID_RE.search(a.attributes.get("href") or "") for a in row.css("a[href]"))
        match = next(filter(None, matches), None)
    else:
        match = TEAM_ID_RE.search(row.attributes.get("onclick") or "")
    if match is None:
        raise ParseError(f"challenge ID not found in row: {row.text(strip=True)!r}")

    return match.group(1)


def parse_overview(
    html: str, challenge_type: ChallengeType, base_url: str
) -> list[ChallengeSummary]:
    """Completed challenges from a project or team challenge overview page."""
    selector = "table#tblChallenges"
    table = _find(LexborHTMLParser(html), selector)
    columns = _columns(table, selector, ("Name", "Project", "Start time", "End time", "Status"))
    challenges = []

    for row in table.css("tr"):
        cells = row.css("td")
        if not cells:
            continue  # header and ad rows
        if _cell(cells, columns, "Status").lower() != "completed":
            continue
        project = _cell(cells, columns, "Project")
        challenge_id = _challenge_id(row, challenge_type)
        path = f"/stats/{URL_SEGMENTS[challenge_type]}/team/list/{challenge_id}/rank"
        challenges.append(
            ChallengeSummary(
                challenge_type=challenge_type,
                name=_cell(cells, columns, "Name"),
                project_name=project if project not in ("", "-") else None,
                start_at=_parse_date(_cell(cells, columns, "Start time")),
                end_at=_parse_date(_cell(cells, columns, "End time")),
                url=urljoin(base_url, path),
            )
        )

    return challenges


def parse_challenge(html: str) -> list[TeamPlacement]:
    """Return teams placed 1st to 3rd, including ties; return [] for an empty results page.

    The place comes from the Rank column (team challenges); without it (project challenges) it is
    competition ranking by Total credit: equal credit gives the same place ("1, 1, 3").
    """
    selector = "table#tblStats"
    table = _find(LexborHTMLParser(html), selector)
    columns = _columns(table, selector, ("Team Name", "Total credit"))
    teams = []
    placements = []

    for row in table.css('tr[id^="rank_"]'):
        cells = row.css("td")
        name = _cell(cells, columns, "Team Name")
        score = _parse_int(_cell(cells, columns, "Total credit"), "total credit")
        if "rank" in columns:
            rank = _parse_int(_cell(cells, columns, "Rank"), "rank")
            placements.append(TeamPlacement(name, rank, score))
        else:
            teams.append((name, score))

    if "rank" not in columns:
        teams.sort(key=lambda team: team[1], reverse=True)

        for position, (name, score) in enumerate(teams, start=1):
            same_as_previous = placements and placements[-1].score == score
            placements.append(
                TeamPlacement(name, placements[-1].place if same_as_previous else position, score)
            )

    return [p for p in placements if p.place <= PODIUM_PLACES]
