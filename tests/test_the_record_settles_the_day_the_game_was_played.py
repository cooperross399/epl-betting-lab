"""The board is a forward window, so the day it was published is not match day.

`web/settle_results.py` read `history/<settle date>.json` -- the board
*published* that day -- and graded it against that day's finals. Every board
this repository has ever frozen carries fixtures still to come: the copy filed
under 2026-09-28 holds the 2026-10-10 through 2026-10-12 fixtures, and so do
its seven neighbours. So the two sides of the join never had a fixture in
common, `results.json` has carried `picks 0-0-0` since the page went up, and
the accompanying notice said "The games were played but no final was available
when this ran" about games eleven days away.

Nothing caught it because no test ran `main` against a board with fixtures in
it. The one end-to-end fixture froze `"games": []`, which settles to zero
whatever the selection rule is.

Selection is now on each fixture's own `kickoff`, across every frozen board.
`test_keying_on_the_filed_date_settles_nothing` is the control: it runs the old
rule over the same inputs and shows it grading none of them.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTLE = PROJECT_ROOT / "web" / "settle_results.py"
BUILDER = PROJECT_ROOT / "web" / "build_board_json.py"
HISTORY = PROJECT_ROOT / "web" / "site_history.py"

SPORT = "epl"

#: The real shape, from https://epl.maverickhightower.com/data/history/.
#: Published 2026-09-28, covering fixtures 12 to 14 days later.
PUBLISHED = "2026-09-28"
KICKOFFS = {"401879268": "2026-10-10", "401878774": "2026-10-11", "401879267": "2026-10-12"}


def _module():
    spec = importlib.util.spec_from_file_location("settle_results", SETTLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _board(generated: str = "2026-09-28T09:23:31Z", over_label: str = "Over 2.5") -> dict:
    """A board as actually published: fixtures spanning three later dates."""
    return {
        "season": "2026-27",
        "generatedAt": generated,
        "windowLabel": "2026-10-10 through 2026-10-12",
        "windowStart": "2026-10-10",
        "teams": {
            "ARS": {"name": "Arsenal"}, "LEE": {"name": "Leeds United"},
            "HUL": {"name": "Hull City"}, "EVE": {"name": "Everton"},
            "COV": {"name": "Coventry City"}, "NEW": {"name": "Newcastle United"},
        },
        "games": [
            {"id": "401879268", "kickoff": "2026-10-10T11:30Z",
             "home": {"abbr": "ARS", "winProb": 0.6}, "away": {"abbr": "LEE", "winProb": 0.2},
             "drawProb": 0.2, "total": {"overProb": 0.61},
             "pick": {"market": "total_2_5", "label": over_label}},
            {"id": "401878774", "kickoff": "2026-10-11T13:00Z",
             "home": {"abbr": "HUL", "winProb": 0.3}, "away": {"abbr": "EVE", "winProb": 0.45},
             "drawProb": 0.25, "total": {"overProb": 0.4},
             "pick": {"market": "btts", "label": "Both teams score"}},
            {"id": "401879267", "kickoff": "2026-10-12T19:00Z",
             "home": {"abbr": "COV", "winProb": 0.35}, "away": {"abbr": "NEW", "winProb": 0.4},
             "drawProb": 0.25, "total": {"overProb": 0.52},
             "pick": {"market": "draw_no_bet", "label": "Newcastle United draw no bet"}},
        ],
    }


def _freeze(tmp_path: Path, name: str, board: dict) -> Path:
    hist = tmp_path / "history"
    hist.mkdir(exist_ok=True)
    (hist / f"{name}.json").write_text(json.dumps(board), encoding="utf-8")
    return hist


def _settle(tmp_path: Path, day: str, finals: dict) -> dict:
    module = _module()
    module.finals = lambda sport, d: finals
    code = module.main(["--data", str(tmp_path), "--sport", SPORT, "--date", day])
    assert code == 0
    return json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))


#: Arsenal 2-1 Leeds: over 2.5 lands, home side wins.
ARS_LEE = {"401879268": {"home": 2, "away": 1, "finish": "REG"}}


def test_a_fixture_is_settled_on_the_day_it_kicked_off(tmp_path) -> None:
    """The board filed under 2026-09-28 is graded on 2026-10-10."""
    _freeze(tmp_path, PUBLISHED, _board())
    written = _settle(tmp_path, KICKOFFS["401879268"], ARS_LEE)

    assert len(written["games"]) == 1, (
        "the fixture kicked off on the settle date and was published on a board "
        "filed under an earlier one; selecting on the filed date misses it"
    )
    assert written["games"][0]["pick"]["result"] == "win"
    assert written["summary"]["picks"] == {"w": 1, "l": 0, "p": 0}
    assert written["notice"] is None
    # The Results page renders names from this table; the board that carried
    # the fixture is the one that has them, and with several boards in play it
    # is no longer whichever file happened to be opened.
    assert {"ARS", "LEE"} <= set(written["teams"]), "the settled sides have no names"


def test_keying_on_the_filed_date_settles_nothing(tmp_path) -> None:
    """The control. The old rule, run over the same inputs, grades none of them.

    This is the whole defect in one assertion: for any settle date, the board
    filed under it holds fixtures for other dates, so the intersection with
    that date's finals is empty.
    """
    hist = _freeze(tmp_path, PUBLISHED, _board())
    finals_by_day = {
        "2026-09-28": {}, "2026-10-10": ARS_LEE,
        "2026-10-11": {"401878774": {"home": 1, "away": 1, "finish": "REG"}},
        "2026-10-12": {"401879267": {"home": 0, "away": 2, "finish": "REG"}},
    }
    for day, finals in finals_by_day.items():
        filed = hist / f"{day}.json"
        board = json.loads(filed.read_text(encoding="utf-8")) if filed.exists() else {"games": []}
        graded = [g for g in board.get("games", []) if str(g.get("id")) in finals]
        assert graded == [], (
            f"the old rule graded something on {day}; if the board filed under a "
            "date can contain that date's fixtures, the control is not reproducing "
            "the defect and the regression it guards is not pinned"
        )


def test_every_day_of_the_window_settles_not_just_the_first(tmp_path) -> None:
    """A board spans three dates. Filing it under one must not orphan the rest.

    Even once the filing was consistent -- `site_history.py` names the frozen
    copy after `windowStart` -- a rule that reads one file per settle date can
    only ever reach the window's first day. Four of the ten fixtures on the
    live board kick off after it.
    """
    settled = {}
    for gid, day in KICKOFFS.items():
        tmp = tmp_path / day
        tmp.mkdir()
        _freeze(tmp, PUBLISHED, _board())
        finals = {gid: {"home": 2, "away": 1, "finish": "REG"}}
        written = _settle(tmp, day, finals)
        settled[day] = [g["id"] for g in written["games"]]

    assert settled == {day: [gid] for gid, day in KICKOFFS.items()}, (
        "each of the window's three dates must settle its own fixture"
    )


def test_the_pick_graded_is_the_one_published_first(tmp_path) -> None:
    """A later board must not be able to replace a pick that already ran.

    `live_clv.first_recommendations` is the repository's convention and the
    reason is the same here: the record owes an answer for what was
    advertised, so a board frozen after a price moved cannot quietly improve
    it. Ordering is on `generatedAt`, not on the filename -- the two writers
    disagreed about the filename, so it cannot carry this.
    """
    hist = _freeze(tmp_path, PUBLISHED, _board(over_label="Over 2.5"))
    # Filed under a LATER name but generated EARLIER, so filename order and
    # publication order disagree and only one of them is right.
    (hist / "2026-09-30.json").write_text(
        json.dumps(_board(generated="2026-09-20T00:00:00Z", over_label="Under 2.5")),
        encoding="utf-8",
    )
    written = _settle(tmp_path, KICKOFFS["401879268"], ARS_LEE)

    pick = written["games"][0]["pick"]
    assert pick["label"] == "Under 2.5", "the earliest publication is the one on the record"
    assert pick["result"] == "loss", "Arsenal 2-1 Leeds is three goals; Under 2.5 lost"
    assert written["summary"]["picks"] == {"w": 0, "l": 1, "p": 0}


def test_a_day_with_no_fixture_does_not_claim_the_games_were_played(tmp_path) -> None:
    """The old notice asserted the opposite of what had happened.

    With no fixture kicking off, `games` was empty for the same reason it was
    always empty, and the notice read "The games were played but no final was
    available when this ran; the next build settles them." None of that is
    true of a date with no fixture, and no build settles them.
    """
    _freeze(tmp_path, PUBLISHED, _board())
    written = _settle(tmp_path, "2026-10-13", {})

    notice = written["notice"]
    assert "kicked off" in notice and "2026-10-13" in notice
    assert "were played" not in notice, f"claims games were played: {notice!r}"
    assert written["games"] == [] and written["summary"] == {}


def test_a_played_fixture_with_no_final_still_says_so(tmp_path) -> None:
    """The retry notice is still needed -- for the case it was written for."""
    _freeze(tmp_path, PUBLISHED, _board())
    written = _settle(tmp_path, KICKOFFS["401879268"], {})

    assert "no final was available" in written["notice"]
    assert written["games"] == []


def _string_constants(path: Path, func: str) -> set[str]:
    """Every string literal inside one function. Comment-immune, by parsing.

    A source grep cannot do this job here: the comment left in place of the
    removed writer explains the duplicate and names `history` while doing so.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            return {
                n.value for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
            }
    raise AssertionError(f"{path.name} has no {func}()")


def test_one_writer_freezes_the_board_and_it_is_the_one_keyed_to_the_window() -> None:
    """Two write-once writers filed the same board under two names at once.

    `build_board_json.py` used the publish date and `site_history.py` used
    `board_date()`, the window start. Both ran every build, so the Archive
    carried seven entries for 2026-09-23 through 09-29 that were all the same
    ten fixtures, plus an eighth filed as 2026-10-10.json -- and settlement
    read the publish-date copy, which is what made the join impossible.

    The freezer is `site_history.py`, which also rebuilds `history/index.json`
    from what it finds, so the index and the boards cannot disagree.
    """
    assert "history" not in _string_constants(BUILDER, "main"), (
        "build_board_json.main writes under history/ again; that is a second "
        "record of the same board under a different name"
    )
    assert "history" in _string_constants(HISTORY, "main"), (
        "site_history.main no longer freezes the board, so nothing does"
    )
