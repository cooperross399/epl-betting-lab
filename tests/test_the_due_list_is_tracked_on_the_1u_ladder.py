"""The Due List is tracked season long as if each entry were bet on the 1u ladder.

The NHL lab's rule (2026-10-09, Cooper: "tracked season long on the website as
if we bet .25u on each one every night"), brought to EPL on 2026-10-31, and on
the 1u ladder since 2026-11-21 (Cooper: "use the due list ladder style pricing
but with 1u as the main instead of .25u"). Nothing is bet and none of it
reaches the card. An entry with a staged price carries `units` (1u up to
+199, 0.6u / 0.4u / 0.2u from +200, at that price; a push 0); a void (he did not play), an ungraded
entry or one with no price carries None and is "not posted": graded for the
hit rate, no units.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _settle():
    spec = importlib.util.spec_from_file_location("settle_due_quarter", ROOT / "web" / "settle_results.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _game(goals: int):
    stats = {"appearances": 1, "totalGoals": goals}
    return {"home": {"abbr": "NEW"}, "away": {"abbr": "EVE"}}, {
        "home": [{"id": "9", "name": "isak", "stats": stats}], "away": []
    }


def _entry(price=250):
    return {"player": "Isak", "playerId": "9", "team": "NEW", "market": "goals", "line": 0.5, "price": price}


def test_a_winning_entry_returns_its_ladder_stake_at_its_price():
    S = _settle()
    g, lines = _game(1)
    row = S.grade_due_entry(_entry(250), g, lines)
    assert row["result"] == "win"
    assert row["units"] == 1.5  # +250 is 0.6u on the 1u ladder: 0.6 x 2.5


def test_a_losing_entry_costs_its_ladder_stake():
    S = _settle()
    g, lines = _game(0)
    assert S.grade_due_entry(_entry(250), g, lines)["units"] == -0.6


def test_an_entry_with_no_price_is_graded_but_not_posted():
    S = _settle()
    g, lines = _game(1)
    row = S.grade_due_entry(_entry(None), g, lines)
    assert row["result"] == "win" and row["units"] is None


def test_the_night_and_the_season_carry_units_and_the_stake():
    S = _settle()
    rows = [
        {"result": "win", "market": "goals", "price": 250, "units": 1.5},
        {"result": "loss", "market": "goals", "price": 120, "units": -1.0},
        {"result": "win", "market": "goals", "units": None},
        {"result": "void", "market": "goals", "units": None},
    ]
    tallies = S.due_tallies(rows)
    assert tallies["stake"] == S.DUE_STAKE == 1.0
    assert tallies["units"] == 0.5
    assert tallies["staked"] == 1.6, "units risked, not a count: 0.6u at +250 and 1u at +120"


def test_the_season_sums_the_nights_units():
    source = (ROOT / "web" / "settle_results.py").read_text()
    season = source.split("def season_record", 1)[1] if "def season_record" in source else source
    assert 'due["units"]' in season and 'due["staked"]' in season


def test_the_due_list_is_priced_after_the_props_prices_are_bought():
    text = (ROOT / ".github/workflows/matchday-refresh.yml").read_text()
    props = text.index("- name: Refresh the props card")
    block = text[props:].split("\n      - name:", 1)[0]
    assert "scripts/build_due_list.py" in block
