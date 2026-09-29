"""The corner markets' wiring was guarded by a substring grep and nothing ran it.

`TestTheCardEvaluatesEveryPriceableMarket` is six assertions of the form
`assert "evaluate_count_market(" in source`. Its own docstring says it exists
because "Five markets were modelled, registered, fetched and validated, and
still produced no picks because nothing evaluated them" — which is exactly the
failure a text grep cannot see.

Line tracing showed the block those strings describe is executed by no test in
the suite: the only two tests that call `run_thursday_best_bets_report` both
expect it to raise well before reaching it. Changing `if count_models:` to
`if not count_models:` — which in production deletes corners_1x2,
corners_total_9_5 and corners_total_10_5 from every Thursday card, and corners
are 23 of the first 42 best bets ever published — passed all 2,440 tests.

This runs the report.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epl_betting_lab import dashboard_actions
from epl_betting_lab.dashboard_actions import run_thursday_best_bets_report

TEAMS = ("Arsenal", "Chelsea", "Liverpool", "Everton")


def _matches(n: int = 160) -> pd.DataFrame:
    """Scorelines with the corner and card columns that ship beside them.

    `HC`/`AC` and `HY`/`AY` are the real Football-Data spellings; a frame
    without them yields no models, which is the state every existing test
    left the card in.
    """
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n):
        home = TEAMS[i % 4]
        away = TEAMS[(i // 4 + 1) % 4]
        if home == away:
            away = TEAMS[(i + 2) % 4]
        rows.append(
            {
                "date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "home_team": home,
                "away_team": away,
                "home_goals": int(rng.poisson(1.4)),
                "away_goals": int(rng.poisson(1.1)),
                "HC": int(rng.poisson(5.5)),
                "AC": int(rng.poisson(4.5)),
                "HY": int(rng.poisson(1.8)),
                "AY": int(rng.poisson(2.0)),
            }
        )
    return pd.DataFrame(rows)


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": "2026-08-21", "home_team": "Arsenal", "away_team": "Chelsea"}]
    )


def _odds(tmp_path: Path) -> Path:
    """A corners price, and a 1x2 price beside it as the control column."""
    path = tmp_path / "current_odds.csv"
    pd.DataFrame(
        [
            {
                "date": "2026-08-21", "home_team": "Arsenal", "away_team": "Chelsea",
                "market": "corners_1x2", "selection": selection,
                "american_odds": odds, "book": "FanDuel",
            }
            for selection, odds in (("home", "+250"), ("draw", "+260"), ("away", "+250"))
        ]
        + [
            {
                "date": "2026-08-21", "home_team": "Arsenal", "away_team": "Chelsea",
                "market": "1x2", "selection": selection,
                "american_odds": odds, "book": "FanDuel",
            }
            for selection, odds in (("home", "+150"), ("draw", "+250"), ("away", "+300"))
        ]
    ).to_csv(path, index=False)
    return path


@pytest.fixture
def _wired(monkeypatch):
    matches = _matches()
    monkeypatch.setattr(dashboard_actions, "load_matches", lambda *a, **k: matches)
    monkeypatch.setattr(
        dashboard_actions, "load_matches_with_xg", lambda *a, **k: matches
    )
    monkeypatch.setattr(
        dashboard_actions, "load_upcoming_fixtures", lambda *a, **k: _fixtures()
    )
    return matches


def _considered(output_dir: Path) -> pd.DataFrame:
    return pd.read_csv(output_dir / "thursday_best_bets.csv")


class TestTheCountMarketsReachTheCard:
    def test_a_corner_market_is_evaluated(self, tmp_path: Path, _wired) -> None:
        """The assertion the grep could not make.

        It does not require a corner bet to be SELECTED — that depends on
        prices and edges and would make this a flaky test of the strategy.
        It requires the market to have been considered at all.
        """
        output_dir = tmp_path / "outputs"
        run_thursday_best_bets_report(_odds(tmp_path), output_dir, force=True)

        considered = _considered(output_dir)
        assert "corners_1x2" in set(considered["market"]), (
            "the corner block did not run; `if count_models:` is the line "
            "that decides, and no test executed it"
        )

    def test_the_control_a_dataset_without_corner_columns_yields_none(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Without this, a card that always listed corners would pass above.

        It is also the behaviour the comment promises: "A dataset without
        them yields no models and therefore no rows, rather than a failure."
        """
        bare = _matches().drop(columns=["HC", "AC", "HY", "AY"])
        monkeypatch.setattr(dashboard_actions, "load_matches", lambda *a, **k: bare)
        monkeypatch.setattr(
            dashboard_actions, "load_matches_with_xg", lambda *a, **k: bare
        )
        monkeypatch.setattr(
            dashboard_actions, "load_upcoming_fixtures", lambda *a, **k: _fixtures()
        )

        output_dir = tmp_path / "outputs"
        run_thursday_best_bets_report(_odds(tmp_path), output_dir, force=True)

        considered = _considered(output_dir)
        assert "corners_1x2" not in set(considered["market"])
        assert not considered.empty, "the run should still produce the other markets"
