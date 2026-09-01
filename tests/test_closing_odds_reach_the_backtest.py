"""Closing odds are kept from Football-Data and reach every backtested bet.

They were being dropped when the dataset was built, so the backtest asked for
a column that never existed and every CLV figure in the project was blank.
"""

from __future__ import annotations

import pandas as pd

from epl_betting_lab.backtest.walk_forward import _closing


def test_the_market_average_close_is_preferred_then_bet365():
    game = pd.Series({"AvgCH": 2.10, "B365CH": 2.05})
    assert _closing(game, "AvgCH", "B365CH") == 2.10
    game = pd.Series({"AvgCH": float("nan"), "B365CH": 2.05})
    assert _closing(game, "AvgCH", "B365CH") == 2.05


def test_no_close_at_all_is_none_not_a_crash():
    game = pd.Series({"AvgH": 2.0})
    assert _closing(game, "AvgCH", "B365CH") is None


def test_the_fetcher_keeps_every_closing_column():
    import inspect
    from epl_betting_lab.data import fetch_football_data as mod

    source = inspect.getsource(mod)
    for column in ("AvgCH", "AvgCD", "AvgCA", "AvgC>2.5", "AvgC<2.5", "B365CH", "B365C>2.5"):
        assert f'"{column}"' in source, column
