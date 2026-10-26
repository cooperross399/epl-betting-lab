"""Double chance and draw-no-bet on the xG ratings vs the card's ratings, on bought prices."""
import subprocess, io
import pandas as pd
from epl_betting_lab.data.loaders import load_matches_with_xg
from epl_betting_lab.models.poisson_goals import TOTALS_RATINGS, CARD_RATINGS
from epl_betting_lab.reports import derived_market_backtest as d

raw = subprocess.run(["git", "show", "origin/odds-history:historical_market_odds.csv"], capture_output=True, text=True, check=True).stdout
odds = pd.read_csv(io.StringIO(raw), low_memory=False)
odds = odds[odds.market.isin(["double_chance", "draw_no_bet"])]
matches = load_matches_with_xg()
for name, cfg in (("card ratings (legacy)", CARD_RATINGS), ("xG ratings", TOTALS_RATINGS)):
    d.CARD_RATINGS = cfg
    result = d.build_backtest(odds, matches)
    print("=====", name)
    print(d.summarize(result).to_string())
