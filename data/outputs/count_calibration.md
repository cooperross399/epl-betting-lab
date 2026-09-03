# Corner market calibration

Walk-forward: each prediction made by a model fitted only on the matches
before it, judged against the corner counts Football-Data ships on the
same rows. No prices are involved here — but they DO exist, contrary to
what this report used to say. The provider sells historical corner
prices, and `data/outputs/derived_market_backtest.md` now measures the
corner rule against money at books that can be bet. Calibration is the
precondition; that report is the test.

Corners are the majority of the live card. Before this report their whole
validation was synthetic unit tests plus six real-data checks skipped in
CI, and those check the fit against league averages rather than whether a
stated probability happens that often.

`gap_points` is observed minus predicted. A bad number here is a reason to
stake less, never a licence to fit the model until it moves:
docs/why_better_calibration_lost_money.md records a change that improved
calibration everywhere and cost 140 units.

| market             | band    |   matches |   predicted |   observed |   gap_points |    brier |   logloss |
|:-------------------|:--------|----------:|------------:|-----------:|-------------:|---------:|----------:|
| corners_1x2        | 0-30%   |       469 |        14.5 |       14.9 |          0.4 | nan      |  nan      |
| corners_1x2        | 30-45%  |       159 |        37.2 |       41.5 |          4.3 | nan      |  nan      |
| corners_1x2        | 45-55%  |        94 |        49.6 |       41.5 |         -8.1 | nan      |  nan      |
| corners_1x2        | 55-70%  |       140 |        61.4 |       61.4 |          0   | nan      |  nan      |
| corners_1x2        | 70-101% |        62 |        78   |       75.8 |         -2.2 | nan      |  nan      |
| corners_1x2        | ALL     |       924 |        33.3 |       33.3 |         -0   |   0.1753 |    0.5255 |
| corners_total_10_5 | 30-45%  |       149 |        41.8 |       40.3 |         -1.5 | nan      |  nan      |
| corners_total_10_5 | 45-55%  |       317 |        50   |       49.8 |         -0.1 | nan      |  nan      |
| corners_total_10_5 | 55-70%  |       150 |        58.2 |       60   |          1.8 | nan      |  nan      |
| corners_total_10_5 | ALL     |       616 |        50   |       50   |          0   |   0.2415 |    0.676  |
| corners_total_9_5  | 30-45%  |       226 |        39.8 |       39.4 |         -0.4 | nan      |  nan      |
| corners_total_9_5  | 45-55%  |       162 |        50   |       50   |          0   | nan      |  nan      |
| corners_total_9_5  | 55-70%  |       226 |        60.2 |       60.6 |          0.4 | nan      |  nan      |
| corners_total_9_5  | ALL     |       616 |        50   |       50   |          0   |   0.2417 |    0.6763 |
