# No external strength rating

`src/epl_betting_lab/data/fetch_clubelo.py` shipped on day one, was imported by
nothing, and is now deleted. This records why, so the question is not reopened
from scratch.

## It was never wired in

Nothing in `src/`, `scripts/`, `app.py` or the workflows ever imported it. It
fetched ClubElo's CSV endpoints to `data/raw/` and stopped there — no join to
Football-Data's team names, no use in any model, no test.

## It is unreachable from here

On 2026-09-01 and again on 2026-09-02, every request timed out:

```
https://api.clubelo.com/2026-08-27   http=000  bytes=0  time=25.0s
https://api.clubelo.com/Arsenal      http=000  bytes=0  time=25.0s
host api.clubelo.com  ->  37.128.134.74
```

DNS resolves and TCP does not connect. That is consistent with the service
being down and equally consistent with this network blocking it, and the two
cannot be told apart from here. So this is not a finding that ClubElo is gone —
only that it cannot be built against from this machine.

## And it is unlikely to be worth much

The reason to blend an external rating is to anchor a model that has nothing
else to check itself against. This model now has opponent-adjusted attack and
defence with a 365-day half-life, fitted on Understat expected goals, scoring
0.9835 log loss on 1X2 against the closing market's 0.9654 —
`docs/no_edge_out_of_sample.md`. An Elo built from the same public results
would be largely the same information rearranged, and the honest ceiling on
what it could add is the gap to the market, which is not where this project's
problem lies. Its problem is that a better probability model still lost on
every held-out season, which no additional rating fixes.

## If it is ever revisited

Restore the module from git history (`git log -- src/epl_betting_lab/data/fetch_clubelo.py`),
confirm reachability from a GitHub Actions runner rather than a laptop, and
judge it the way every other change here is judged: threshold-free log loss
first, then a held-out-season bet rule, then closing-line value. An external
rating that improves none of those is decoration.
