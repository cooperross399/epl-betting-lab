"""The Beyond card staked prices its own model calls negative.

`evaluate_total_25_anchored` sets BETTABLE from the anchor LIFT alone — the
blended probability against the de-vigged consensus — and leaves the gate
against the POSTED price to the consumer. Its own comment says so: "The gate
is kept because a row with edge <= 0 is a price this model's own final number
calls negative."

The Premier League card applies it (`_confidence_tier` returns Pass/Avoid at
edge <= 0, `_suggested_units` maps that to 0.0). This card filtered on
`status == "BETTABLE"` and staked every survivor at EXTRA_UNITS, using the
edge only as a sort key.

`out_of_sample.score_rule` applies the same gate by default and its docstring
says it "must stay the default", because "the looser rule is the one that
stakes money on a price the model's own final number says is negative". So
the published out-of-sample figures describe the gated rule, and this card
was running the other one.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.reports import extra_competitions_card as card_module
from epl_betting_lab.reports.extra_competitions_card import build_extra_card

NOW = pd.Timestamp("2026-09-15T12:00:00Z")


def _feed(over: int, under: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "competition": ["UNL"] * 2,
            "observed_at": ["2026-09-15T10:00:00Z"] * 2,
            "provider_event_id": ["e1"] * 2,
            "date": ["2026-09-16"] * 2,
            "home_team": ["France"] * 2,
            "away_team": ["Spain"] * 2,
            "market": ["total_2_5"] * 2,
            "selection": ["over", "under"],
            "book": ["DraftKings"] * 2,
            "american_odds": [over, under],
        }
    )


@pytest.fixture
def _totals_pool(monkeypatch):
    """A pool that prices totals, so the gate is reachable.

    The international pool withholds `total_2_5` outright, which is why this
    went unnoticed: the one competition whose prices are easiest to stub is
    the one where the market never renders.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from test_extra_competitions_card import _stub_international_pool

    _stub_international_pool(monkeypatch)
    monkeypatch.setattr(card_module, "POOL_EXCLUDED_MARKETS", {})
    return monkeypatch


#: Found by sweeping prices inside the juice limit: the anchor lift is
#: positive and the edge against the posted price is not. Thirty-three such
#: combinations staked a selection before this gate existed; this is the
#: worst of them.
NEGATIVE_EDGE_PRICES = (-149, -149)


class TestANegativeEdgeIsNotStaked:
    def test_the_worst_measured_case_is_refused(self, _totals_pool) -> None:
        card = build_extra_card(_feed(*NEGATIVE_EDGE_PRICES), "UNL", now=NOW)

        staked = card.selections
        if not staked.empty:
            assert (pd.to_numeric(staked["calibrated_edge"]) > 0).all(), (
                "a selection is staked at a price the model calls negative"
            )
        assert any("not positive" in note for note in card.notes), card.notes

    def test_the_control_a_positive_edge_still_stakes(self, _totals_pool) -> None:
        """Without this, refusing everything would pass the test above."""
        card = build_extra_card(_feed(-250, 200), "UNL", now=NOW)

        assert not card.selections.empty
        assert (pd.to_numeric(card.selections["calibrated_edge"]) > 0).all()
        assert float(card.selections.iloc[0]["suggested_units"]) > 0

    def test_no_price_in_the_sweep_stakes_a_negative_edge(self, _totals_pool) -> None:
        """The whole band, not the one example.

        A test pinned to a single price pair passes as soon as that pair
        stops clearing for an unrelated reason.
        """
        staked_negative = []
        for over in range(-149, 200, 7):
            for under in range(-149, 200, 7):
                if -100 < over < 100 or -100 < under < 100:
                    continue
                card = build_extra_card(_feed(over, under), "UNL", now=NOW)
                for _, row in card.selections.iterrows():
                    if float(row["calibrated_edge"]) <= 0:
                        staked_negative.append((over, under, row["selection"]))

        assert not staked_negative, (
            f"{len(staked_negative)} negative-edge selection(s) still staked"
        )

    def test_the_sweep_finds_something_to_stake(self, _totals_pool) -> None:
        """The control for the sweep: a gate that emptied every card would
        pass it, and would also be a broken card."""
        staked = 0
        for over in range(-149, 200, 7):
            for under in range(-149, 200, 7):
                if -100 < over < 100 or -100 < under < 100:
                    continue
                staked += len(build_extra_card(_feed(over, under), "UNL", now=NOW).selections)

        assert staked > 0, "the gate refuses every price, which is not the fix"


def test_the_refusal_is_reported_not_silent(_totals_pool) -> None:
    """A section that quietly drops half its selections and one that was
    quoted half as many look identical to a reader."""
    card = build_extra_card(_feed(*NEGATIVE_EDGE_PRICES), "UNL", now=NOW)

    note = next(n for n in card.notes if "not positive" in n)
    assert "total_2_5" in note


def test_an_edge_of_exactly_zero_is_refused(_totals_pool, monkeypatch) -> None:
    """The boundary, which no price sweep can reach.

    Relaxing the gate from `> 0` to `>= 0` survived every test above,
    because an edge of exactly 0.0000 does not fall out of real odds. It is
    still a bet at precisely fair value against the price offered, and the
    Premier League path refuses it: `_confidence_tier` returns Pass/Avoid on
    `edge <= 0`, not `edge < 0`.

    So the row is injected: one market's evaluator returns a BETTABLE
    selection with a zero edge, and the real gate runs on it.
    """
    zero_edge = pd.DataFrame(
        [
            {
                "home_team": "France",
                "away_team": "Spain",
                "market": "total_2_5",
                "selection": "over",
                "american_odds": -110,
                "book": "DraftKings",
                "status": "BETTABLE",
                "calibrated_edge": 0.0,
                "raw_edge": 0.0,
            }
        ]
    )
    monkeypatch.setattr(
        card_module, "evaluate_total_25_anchored", lambda *a, **k: zero_edge
    )
    monkeypatch.setattr(card_module, "evaluate_btts", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(
        card_module, "evaluate_double_chance", lambda *a, **k: pd.DataFrame()
    )
    monkeypatch.setattr(
        card_module, "evaluate_draw_no_bet", lambda *a, **k: pd.DataFrame()
    )

    card = build_extra_card(_feed(-110, -110), "UNL", now=NOW)

    assert card.selections.empty, "a zero edge is fair value, not an edge"
    assert any("not positive" in note for note in card.notes)


def test_the_control_the_same_injection_with_a_positive_edge_stakes(
    _totals_pool, monkeypatch
) -> None:
    """Otherwise the injection itself could be what empties the card."""
    positive = pd.DataFrame(
        [
            {
                "home_team": "France",
                "away_team": "Spain",
                "market": "total_2_5",
                "selection": "over",
                "american_odds": -110,
                "book": "DraftKings",
                "status": "BETTABLE",
                "calibrated_edge": 0.05,
                "raw_edge": 0.05,
            }
        ]
    )
    monkeypatch.setattr(
        card_module, "evaluate_total_25_anchored", lambda *a, **k: positive
    )
    monkeypatch.setattr(card_module, "evaluate_btts", lambda *a, **k: pd.DataFrame())
    monkeypatch.setattr(
        card_module, "evaluate_double_chance", lambda *a, **k: pd.DataFrame()
    )
    monkeypatch.setattr(
        card_module, "evaluate_draw_no_bet", lambda *a, **k: pd.DataFrame()
    )

    card = build_extra_card(_feed(-110, -110), "UNL", now=NOW)

    assert len(card.selections) == 1
    assert float(card.selections.iloc[0]["suggested_units"]) > 0


class TestTheCapSaysWhatItWithheld:
    """The cap withheld 22 of 26 selections and said nothing.

    `MAX_EXTRA_BETS` is 4 and the published card shows exactly four for each
    of UNL, UCL and UEL, so it is saturated on ordinary runs rather than in
    edge cases. It appeared nowhere: not in `card.notes`, not in
    `render_extra_card`, and not in `extra_card_record`, whose per-competition
    block carries only `priced`, `declined` and the POST-cap selection count.

    Worse, the price-gate note added beside it counted refusals taken before
    the cut — and because a refused row always sorts below every positive
    one, those refusals cost the card nothing whenever the cap is saturated.
    The card announced the harmless loss and hid the real one.
    """

    #: Every pairing here is rateable in the stub pool, which holds exactly
    #: France, Germany, Italy, Portugal and Spain. A pairing outside it is
    #: declined as unrated and never reaches the cap, which is what made the
    #: first version of this fixture prove nothing.
    FIXTURES = (
        ("France", "Spain"),
        ("Spain", "France"),
        ("Italy", "Germany"),
        ("Germany", "Italy"),
        ("Portugal", "Spain"),
        ("Spain", "Portugal"),
    )

    def _many(self, n: int) -> pd.DataFrame:
        """`n` rateable fixtures that all clear with a positive edge."""
        rows = []
        for i, (home, away) in enumerate(self.FIXTURES[:n]):
            for selection, odds in (("over", -250), ("under", 200)):
                rows.append(
                    {
                        "competition": "UNL",
                        "observed_at": "2026-09-15T10:00:00Z",
                        "provider_event_id": f"e{i}",
                        "date": "2026-09-16",
                        "home_team": home,
                        "away_team": away,
                        "market": "total_2_5",
                        "selection": selection,
                        "book": "DraftKings",
                        "american_odds": odds,
                    }
                )
        return pd.DataFrame(rows)

    def test_the_card_says_how_many_it_withheld(self, _totals_pool) -> None:
        from epl_betting_lab.reports.extra_competitions_card import MAX_EXTRA_BETS

        card = build_extra_card(self._many(6), "UNL", now=NOW)

        assert len(card.selections) == MAX_EXTRA_BETS, (
            "the cap is not saturated, so this proves nothing about it"
        )
        note = next((n for n in card.notes if "not shown" in n), None)
        assert note is not None, card.notes
        assert str(MAX_EXTRA_BETS) in note

    def test_the_control_nothing_is_said_when_nothing_is_withheld(
        self, _totals_pool
    ) -> None:
        """A cap line on every card would stop being read."""
        card = build_extra_card(_feed(-250, 200), "UNL", now=NOW)

        assert len(card.selections) < 4
        assert not any("not shown" in n for n in card.notes)

    def test_the_refusal_note_does_not_claim_a_cost_it_did_not_have(
        self, _totals_pool
    ) -> None:
        """A refused row sorts below every positive one.

        So where the cap is saturated the gate removed nothing the card
        would have printed, and the note has to say so rather than read as
        "this is what you lost".
        """
        card = build_extra_card(_feed(*NEGATIVE_EDGE_PRICES), "UNL", now=NOW)

        note = next(n for n in card.notes if "not positive" in n)
        assert "sorts below every positive one" in note
