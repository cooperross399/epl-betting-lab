"""A settled record may have a hole in it. It may not name the wrong side.

`selection_label` in `web/build_board_json.py` writes the team NAME it was
handed -- "Newcastle draw no bet", "Notre Dame -4", "Kansas ML". The board
carries abbreviations: NEW, ND, KU. `settle_results.py` shipped comparing the
one against the other, `label.startswith(abbr)`, which is False for almost
every real label, plus a second EPL arm reading `g["_homeName"]` -- a key
nothing in either lab writes, so it evaluated `"" in label`, true of every
string, and every draw-no-bet graded as a home pick whichever side was taken.

Neither failure raises. Both land in results.json as a settled win or loss
against the wrong team, which is the one output of this repository that is
supposed to be beyond argument.

So the side is resolved from the board's own team table, and a label that
cannot be resolved is left ungraded rather than guessed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTLE = PROJECT_ROOT / "web" / "settle_results.py"


def _module():
    spec = importlib.util.spec_from_file_location("settle_results", SETTLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Abbreviations chosen so neither is a prefix of its own team name. That is
#: the whole defect: "alabama".startswith("ala") is true by luck and hid it,
#: while "notre dame".startswith("nd") is false and mis-graded the pick.
BOARD = {
    "teams": {
        "NEW": {"name": "Newcastle", "short": "Newcastle"},
        "WOL": {"name": "Wolves", "short": "Wolves"},
        "ND": {"name": "Notre Dame", "short": "Notre Dame"},
        "NOVA": {"name": "Villanova", "short": "Villanova"},
    },
}
SOCCER = {"id": "1", "home": {"abbr": "NEW"}, "away": {"abbr": "WOL"}}
HOOPS = {"id": "2", "home": {"abbr": "ND"}, "away": {"abbr": "NOVA"}}


@pytest.mark.parametrize(
    "game, label, expected",
    [
        (SOCCER, "Newcastle draw no bet", "home"),
        (SOCCER, "Wolves draw no bet", "away"),
        (HOOPS, "Notre Dame −4", "home"),
        (HOOPS, "Villanova +4", "away"),
        (HOOPS, "Notre Dame ML", "home"),
        (HOOPS, "Villanova ML", "away"),
    ],
)
def test_the_side_comes_from_the_team_table(game, label, expected) -> None:
    assert _module().side_named(label.lower(), game, BOARD["teams"]) == expected


def test_an_unresolvable_label_is_left_ungraded() -> None:
    """Better a gap in the record than a confident entry for the opponent."""
    module = _module()
    assert module.side_named("some market nobody mapped", HOOPS, BOARD["teams"]) is None
    pick = {"kind": "bet", "market": "moneyline", "label": "Some Other School ML"}
    assert module.grade_pick("cbb", pick, HOOPS, 70, 60, BOARD["teams"]) is None


def test_an_away_draw_no_bet_that_won_is_not_settled_as_a_loss() -> None:
    """The shipped expression returned home for every EPL draw-no-bet.

    Home losing 0-1 with the AWAY side picked is a win. The `"" in label` arm
    called it a loss, and nothing in the output said which side it had read.
    """
    pick = {"kind": "bet", "market": "draw_no_bet", "label": "Wolves draw no bet"}
    assert _module().grade_pick("epl", pick, SOCCER, 0, 1, BOARD["teams"]) == "win"


def test_a_home_spread_is_not_settled_against_the_away_side() -> None:
    """"notre dame".startswith("nd") is False, so this graded as away.

    Notre Dame -4 winning by 10 covers. Read as the away side it is scored
    -10 + 4, a loss.
    """
    pick = {"kind": "bet", "market": "spread", "label": "Notre Dame −4", "line": -4}
    assert _module().grade_pick("cbb", pick, HOOPS, 80, 70, BOARD["teams"]) == "win"


def _executable_source() -> str:
    """The file with its comments and docstrings gone, other strings kept.

    This guard greps for two expressions the replacing function's own
    docstring necessarily quotes -- the same shape as the workflow comment
    that trips its own `contents: write` check -- so raw text caught the
    explanation instead of the code.

    The first fix tokenized away every STRING, which silently removed the
    thing being hunted: `_homeName` only ever appears as a string literal
    inside `.get()`. Restoring the discarded arm did not fail this test; only
    the behavioural one below caught it. Parsing and dropping just the
    docstrings keeps real literals visible.
    """
    import ast

    tree = ast.parse(SETTLE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            body.pop(0)
    return ast.unparse(tree)


def test_neither_discarded_arm_is_still_deciding_the_side() -> None:
    """Pins the two specific expressions this file exists to remove.

    `_homeName` is written by nothing in either lab, so any read of it is the
    always-true arm coming back.
    """
    code = _executable_source()
    assert "_homeName" not in code, (
        "settle_results.py reads _homeName again, which nothing writes -- the "
        "arm evaluates an empty string against the label and grades every "
        "pick as the home side"
    )
    normalised = code.replace("'", '"').replace(" ", "")
    assert 'label.startswith(g["home"]["abbr"]' not in normalised, (
        "the side is being decided by abbreviation prefix again, which is "
        "False for every label that carries a team name"
    )
