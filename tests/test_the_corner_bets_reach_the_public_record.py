"""Every BET the card publishes is a corner market, and none of them were graded.

`settle_results.grade_pick` returned None for anything starting `corners`, with
the note "corners / double chance need feeds the site does not have". ESPN's
scoreboard indeed carries no corner counts -- but its per-match summary does,
as `wonCorners` per side, on the same host and free.

So the public record was structurally incapable of reporting on a bet. Of the
ten picks on the 2026-10-10 board, five are bets and all five are corners; the
two `draw_no_bet` picks are leans and the two `double_chance` picks are passes.
Graded only as far as it could reach, the page would have published a model
record made entirely of leans while advertising bets.

The settlement rule is the lab's own, from `card_scoreboard.settle`. The code is
deliberately separate -- this script is stdlib-only and ships to four repos --
and these tests pin its behaviour directly rather than comparing the two copies,
with one exception noted where a disagreement would put two contradictory
records of the same bet in public.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTLE = PROJECT_ROOT / "web" / "settle_results.py"
SPORT = "epl"

#: FUL 3, MAN 13 on 2026-09-20 -- a real match, so the numbers are not invented.
EVENT = "401878777"


def _module():
    spec = importlib.util.spec_from_file_location("settle_results", SETTLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _board(market: str, label: str, kind: str = "bet") -> dict:
    return {
        "season": "2026-27",
        "generatedAt": "2026-09-18T09:00:00Z",
        "windowLabel": "2026-09-20 through 2026-09-20",
        "teams": {"FUL": {"name": "Fulham"}, "MUN": {"name": "Man United"}},
        "games": [{
            "id": EVENT, "kickoff": "2026-09-20T15:30Z",
            "home": {"abbr": "FUL", "winProb": 0.4}, "away": {"abbr": "MUN", "winProb": 0.35},
            "drawProb": 0.25, "total": {"overProb": 0.55},
            "pick": {"kind": kind, "market": market, "label": label, "price": -141, "units": 0.1},
        }],
    }


def _run(tmp_path: Path, market: str, label: str, *, home: int = 3, away: int = 13,
         kind: str = "bet", summary_ok: bool = True) -> tuple[dict, list[str]]:
    """Settle one fixture, stubbing the HOST and recording every URL asked for.

    Both the scoreboard and the summary go through `fetch`, so the request log
    is what proves a corner pick costs exactly one extra request and a
    non-corner pick costs none.
    """
    module = _module()
    (tmp_path / "history").mkdir(exist_ok=True)
    (tmp_path / "history" / "2026-09-20.json").write_text(
        json.dumps(_board(market, label, kind)), encoding="utf-8"
    )
    asked: list[str] = []

    def _fetch(url, timeout=30):
        asked.append(url)
        if "scoreboard" in url:
            return {"events": [{
                "id": EVENT, "status": {"type": {"completed": True, "detail": "FT"}},
                "competitions": [{"competitors": [
                    {"homeAway": "home", "score": "1"}, {"homeAway": "away", "score": "1"}]}],
            }]}
        if not summary_ok:
            raise OSError("summary unavailable")
        return {"boxscore": {"teams": [
            {"homeAway": "home", "statistics": [{"name": "wonCorners", "displayValue": str(home)}]},
            {"homeAway": "away", "statistics": [{"name": "wonCorners", "displayValue": str(away)}]},
        ]}}

    module.fetch = _fetch
    assert module.main(["--data", str(tmp_path), "--sport", SPORT, "--date", "2026-09-20"]) == 0
    return json.loads((tmp_path / "results.json").read_text(encoding="utf-8")), asked


def test_a_corner_total_is_graded_from_the_counts(tmp_path) -> None:
    """Sixteen corners is over 10.5 and over 9.5, and not under either.

    The last two cases put the total on the whole number below the line -- ten
    against 10.5 -- which is the only arrangement that can tell 10.5 from 10.
    The line is parsed out of the market key, and a parse that dropped the
    half would settle those as a push and read identically on every other
    case here.
    """
    for market, label, home, away, expected in (
        ("corners_total_10_5", "Over 10.5 corners", 3, 13, "win"),
        ("corners_total_10_5", "Under 10.5 corners", 3, 13, "loss"),
        ("corners_total_9_5", "Over 9.5 corners", 3, 13, "win"),
        ("corners_total_9_5", "Under 9.5 corners", 3, 13, "loss"),
        ("corners_total_10_5", "Under 10.5 corners", 4, 6, "win"),
        ("corners_total_10_5", "Over 10.5 corners", 4, 6, "loss"),
    ):
        tmp = tmp_path / f"{market}-{label}-{home}{away}".replace(" ", "_").replace(".", "")
        tmp.mkdir()
        written, _ = _run(tmp, market, label, home=home, away=away)
        assert written["games"][0]["pick"]["result"] == expected, (market, label, home, away)
        assert written["summary"]["ungraded"] == 0


def test_the_side_with_more_corners_wins_the_1x2(tmp_path) -> None:
    for label, expected in (("Man United most corners", "win"), ("Fulham most corners", "loss")):
        tmp = tmp_path / label.replace(" ", "_")
        tmp.mkdir()
        written, _ = _run(tmp, "corners_1x2", label)
        assert written["games"][0]["pick"]["result"] == expected, label


def test_an_equal_corner_count_loses_a_side_selection_it_does_not_push(tmp_path) -> None:
    """`corners_1x2` is a THREE-way market, so the tie is its own outcome.

    `market_eligibility` lists it as ("home", "draw", "away"). Settling the tie
    as a push would return a stake the book kept, and the published ROI would
    be wrong in the model's favour on exactly the market that carries the card.
    """
    written, _ = _run(tmp_path, "corners_1x2", "Fulham most corners", home=6, away=6)
    assert written["games"][0]["pick"]["result"] == "loss"
    assert written["summary"]["picks"] == {"w": 0, "l": 1, "p": 0}


def test_the_two_records_agree_about_the_tie(tmp_path) -> None:
    """The one place the separate copies must not diverge.

    The code is deliberately duplicated -- stdlib-only, four repos -- and no
    test here demands they match line for line. This asserts one shared
    semantic, because a disagreement would put two contradictory records of
    the same bet in public: the lab's scoreboard and the site's Results page.
    """
    from epl_betting_lab.reports.card_scoreboard import settle

    lab = settle("corners_1x2", "home", 1, 1, home_corners=6, away_corners=6)
    assert lab is False, "the lab settles a tied corner count as a loss for the side"

    written, _ = _run(tmp_path, "corners_1x2", "Fulham most corners", home=6, away=6)
    assert written["games"][0]["pick"]["result"] == "loss", (
        "the site's copy pushes where the lab's loses; the same bet now has two "
        "different public records"
    )


def test_a_missing_statistic_is_not_a_zero(tmp_path) -> None:
    """The failure has a direction, which is why it must not be guessed.

    Absent counts read as zero would settle every `Under` as a win whenever the
    feed was down -- a fabricated result, always favouring the card.
    """
    written, _ = _run(tmp_path, "corners_total_10_5", "Under 10.5 corners", summary_ok=False)
    assert written["summary"]["picks"] == {"w": 0, "l": 0, "p": 0}
    assert written["summary"]["ungraded"] == 1, (
        "a pick the record cannot answer for has to be counted, or the page "
        "reports a win rate for a subset it never names"
    )
    # The row carries no pick at all, and that is load-bearing rather than
    # incidental: `resultPick` in web/lib/sports.js mapped every result it did
    # not recognise to "Push" until 2026-10-01, so an ungraded pick reaching
    # the page as `result: null` was published as a returned stake. It now
    # prints "Not graded" (tests/test_an_ungraded_pick_is_never_a_push.py),
    # but the row is still dropped, and the `ungraded` count above, which the
    # strip now prints, is what keeps the pick from vanishing unrecorded.
    assert written["games"][0]["pick"] is None, (
        "an ungraded pick reached the page, which renders an unknown result as Push"
    )


def test_one_side_reporting_corners_is_not_enough(tmp_path) -> None:
    module = _module()
    payload = {"boxscore": {"teams": [
        {"homeAway": "home", "statistics": [{"name": "wonCorners", "displayValue": "5"}]},
        {"homeAway": "away", "statistics": [{"name": "foulsCommitted", "displayValue": "9"}]},
    ]}}
    module.fetch = lambda url, timeout=30: payload
    assert module.corner_counts(SPORT, EVENT) is None, (
        "a half-read total settles a totals line against a number that is not the total"
    )


def test_a_present_but_empty_count_is_not_a_zero() -> None:
    """The stat can be there and say nothing, which is not the same as nought.

    `wonCorners` present with a null or empty `displayValue` is the shape a
    half-populated summary takes, and it is more likely than the stat being
    absent: the boxscore is assembled before every figure in it is known.
    Read as zero it settles every `Under` as a win on a number the feed never
    reported -- the same fabrication as a failed fetch, arriving through a
    successful one.
    """
    module = _module()
    for value in (None, "", "   ", "-"):
        module.fetch = lambda url, timeout=30, v=value: {"boxscore": {"teams": [
            {"homeAway": "home", "statistics": [{"name": "wonCorners", "displayValue": v}]},
            {"homeAway": "away", "statistics": [{"name": "wonCorners", "displayValue": v}]},
        ]}}
        assert module.corner_counts(SPORT, EVENT) is None, f"{value!r} was read as a count"


def test_a_corner_pick_costs_one_extra_request_and_others_cost_none(tmp_path) -> None:
    """The summary is per fixture, so it is fetched only where it is needed."""
    corner = tmp_path / "corner"
    corner.mkdir()
    _, asked = _run(corner, "corners_total_10_5", "Over 10.5 corners")
    assert sum("summary" in u for u in asked) == 1
    assert EVENT in [u.split("event=")[-1] for u in asked if "summary" in u]

    other = tmp_path / "other"
    other.mkdir()
    _, asked = _run(other, "btts", "Both teams score")
    assert not any("summary" in u for u in asked), (
        "a non-corner pick paid for a summary request it has no use for"
    )


def test_a_sport_without_corners_has_no_summary_endpoint() -> None:
    module = _module()
    assert "cbb" not in module.SUMMARY
    called: list[str] = []
    module.fetch = lambda url, timeout=30: called.append(url) or {}
    assert module.corner_counts("cbb", EVENT) is None
    assert called == [], "asked a basketball scoreboard for corners"


def test_a_whole_number_line_pushes(tmp_path) -> None:
    """Defensive, and deliberately so.

    Every line the card quotes today is a half, so a push is impossible by
    construction. Were a whole-number line ever quoted, the absent branch
    would have settled an exact hit as a loss in silence.
    """
    module = _module()
    graded = module.grade_corners(
        "corners_total_10_0", "under 10 corners",
        {"home": {"abbr": "FUL"}, "away": {"abbr": "MUN"}}, {}, {"home": 4, "away": 6},
    )
    assert graded == "push"
