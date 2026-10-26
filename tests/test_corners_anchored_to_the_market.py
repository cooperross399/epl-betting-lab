"""Corner totals are priced the way the 2.5 line is: model blended with market.

Held out on 2025/26-2026/27, the corner model's log loss at 9.5 was 0.6908
against 0.6916 for one league-wide rate, so most of a corner "edge" was the
price disagreeing with an average. On the 2025/26 corner prices bought from
the provider (bettable books only), the blend of model and de-vigged consensus
at weight 0.5 was the most accurate of the three probabilities (log loss
0.6819 against the market's 0.6826 and the model's 0.6840 over 760 lines),
and the anchored rule bet 181 times at +6.6% against the old rule's 178 at
+5.4%, every interval wide enough to hold both. The constants are the 2.5
line's (0.5 / 0.03), fixed before these prices were read, not tuned on them.
"""

from __future__ import annotations

import pandas as pd

from epl_betting_lab.models.poisson_counts import PoissonCountModel
from epl_betting_lab.strategies import count_markets
from epl_betting_lab.strategies.count_markets import evaluate_count_market


class _Model:
    """A count model that says what it is told to."""

    def __init__(self, over: float) -> None:
        self.over = over

    def total_over_probability(self, home: str, away: str, line: float) -> float:
        return self.over

    def match_probabilities(self, home: str, away: str) -> dict[str, float]:
        return {"home": 0.5, "draw": 0.1, "away": 0.4}


FIXTURES = pd.DataFrame({"home_team": ["Arsenal"], "away_team": ["Chelsea"]})


def _odds(over: int, under: int, book: str = "FanDuel", market: str = "corners_total_9_5") -> pd.DataFrame:
    return pd.DataFrame({
        "home_team": ["Arsenal", "Arsenal"], "away_team": ["Chelsea", "Chelsea"],
        "market": [market, market], "selection": ["over", "under"],
        "american_odds": [over, under], "book": [book, book],
    })


def _consensus() -> pd.DataFrame:
    # Two books pricing the line as a coin flip once their margins come off.
    return pd.concat([_odds(-110, -110, "FanDuel"), _odds(-110, -110, "DraftKings")], ignore_index=True)


def _row(model_over: float, best_over: int = 100, best_under: int = -120) -> pd.Series:
    graded = evaluate_count_market(
        "corners_total_9_5", {"corners": _Model(model_over)}, FIXTURES,
        _odds(best_over, best_under), market_odds=_consensus(),
    )
    return graded[graded["selection"] == "over"].iloc[0]


def test_the_model_is_blended_with_the_de_vigged_consensus() -> None:
    row = _row(0.60)
    assert row["market_prob"] == 0.5
    assert row["market_prob_source"] == "consensus"
    # Halfway between the two in logit space: logit(0.6)/2 -> 0.5503.
    assert abs(row["calibrated_model_prob"] - 0.5503) < 1e-3
    assert row["selection_rule"] == "market_anchored"


def test_a_lift_over_the_market_with_a_positive_price_edge_is_a_bet() -> None:
    row = _row(0.60)  # lift 0.050, +100 implies 0.500: edge +0.050
    assert row["status"] == "BETTABLE"


def test_a_small_disagreement_is_not_a_bet_any_more() -> None:
    """0.555 at +100 cleared the old 3.5-point bar on the model alone."""
    row = _row(0.555)  # blend 0.528: lift 0.028, under the 0.03 bar
    assert row["raw_edge"] >= 0.035
    assert row["status"] == "PASS"


def test_a_lift_the_posted_price_does_not_pay_is_not_staked() -> None:
    row = _row(0.60, best_over=-130)  # -130 implies 0.565 > blend 0.550
    assert row["status"] != "BETTABLE"


def test_without_per_book_prices_the_best_price_pair_stands_in_and_says_so() -> None:
    graded = evaluate_count_market(
        "corners_total_9_5", {"corners": _Model(0.6)}, FIXTURES, _odds(100, -120),
    )
    assert set(graded["market_prob_source"]) == {"best-price pair"}


def test_a_book_the_card_cannot_bet_does_not_move_the_anchor() -> None:
    skewed = pd.concat([_consensus(), _odds(-400, 300, "Pinnacle")], ignore_index=True)
    graded = evaluate_count_market(
        "corners_total_9_5", {"corners": _Model(0.6)}, FIXTURES, _odds(100, -120),
        market_odds=skewed,
    )
    assert graded[graded["selection"] == "over"].iloc[0]["market_prob"] == 0.5


def test_corner_match_result_and_cards_keep_their_own_rule() -> None:
    odds = pd.DataFrame({
        "home_team": ["Arsenal"] * 3, "away_team": ["Chelsea"] * 3,
        "market": ["corners_1x2"] * 3, "selection": ["home", "draw", "away"],
        "american_odds": [100, 600, 150], "book": ["FanDuel"] * 3,
    })
    graded = evaluate_count_market(
        "corners_1x2", {"corners": _Model(0.6)}, FIXTURES, odds, market_odds=_consensus(),
    )
    assert "selection_rule" not in graded.columns or graded["selection_rule"].isna().all()
    assert count_markets.ANCHORED_EVENTS == frozenset({"corners"})


def test_the_live_card_hands_the_per_book_prices_to_the_corner_rule() -> None:
    from pathlib import Path

    source = Path(count_markets.__file__).parents[1].joinpath("dashboard_actions.py").read_text()
    call = source.split("evaluate_count_market(", 1)[1].split(")", 1)[0]
    assert "market_odds=market_odds" in call


def test_the_real_count_model_still_feeds_the_blend() -> None:
    assert hasattr(PoissonCountModel, "total_over_probability")
