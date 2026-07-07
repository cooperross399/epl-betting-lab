# EPL Betting Lab Market-Specific Calibration Comparison

This compares the old raw model, the generic shrinkage layer, and the new market-specific calibration settings.

- `generic_calibrated` means the same shrinkage rules for every market.
- `calibrated` means market-specific rules, including stricter total_2_5 thresholds.
- This report uses historical backtest odds only. It does not use live odds, fabricate prices, or place bets.

| market    |   raw_bets |   raw_roi |   generic_calibrated_bets |   generic_calibrated_roi |   calibrated_bets |   calibrated_roi |   bets_filtered_out |   calibrated_profit_units |
|:----------|-----------:|----------:|--------------------------:|-------------------------:|------------------:|-----------------:|--------------------:|--------------------------:|
| 1x2       |        827 |    -0.037 |                       546 |                    0.025 |               546 |            0.025 |                 281 |                     13.72 |
| total_2_5 |        606 |    -0.06  |                       474 |                   -0.077 |                 6 |            0.173 |                 600 |                      1.04 |