# One rating scale across European football

Clubs never move between countries, so nothing links one country's ratings to another's the way promotion links the English divisions. Fitted separately, every league is normalised to its own average and a Spanish rating means nothing against an English one.

European ties are the bridge: matches with results, played between clubs from two different domestic pools.

**18,054 domestic matches** across 11 leagues, **868 European ties** linking them, 281 clubs rated.

## Does the bridged scale carry club-level information?

Walk-forward: fit on everything before a season, predict that season's European ties. The comparison keeps the country gap and throws away the club — it replaces the club's own rating with the mean rating of its own league. Beating that is what shows the scale carries more than a league-level difference a market already knows.

| | RMSE |
|:--|--:|
| Club's own rating, bridged scale | **1.3573** |
| Naive — club = average of its own league | 1.4665 |

**+7.45%**, difference -0.1092, 95% interval **-0.1387 to -0.0798** over 481 held-out ties, resampling ties rather than innings because a tie's two innings share one match and one pair of ratings.

This is the opposite of the English division result, where carrying a club's rating through a promotion was *worse* than discarding it. The difference makes sense: a promoted club becomes a different thing at a higher level, while a Champions League club in Europe is the same side against comparable opposition.

## What this is not

It predicts goals better than a naive prior. **It is not evidence of beating a price.** The Premier League model also predicts goals respectably and carries beta = -0.023 against the closing line — the share of its disagreement with the market that holds information is indistinguishable from zero. Whether these ratings beat a Champions League price needs the closing-line record the price collection is accumulating, not this table.

## Mean rating by country

| Country | League | Clubs | Attack | Defence |
|:--|:--|--:|--:|--:|
| ENG | England — Premier League | 29 | 1.067 | 0.956 |
| GER | Germany — Bundesliga | 27 | 1.057 | 1.037 |
| NED | Netherlands — Eredivisie | 25 | 1.024 | 1.074 |
| FRA | France — Ligue 1 | 26 | 1.023 | 0.992 |
| ESP | Spain — La Liga | 29 | 0.997 | 0.970 |
| TUR | Turkey — Süper Lig | 32 | 0.985 | 1.008 |
| BEL | Belgium — Pro League | 24 | 0.975 | 1.022 |
| SCO | Scotland — Premiership | 14 | 0.973 | 1.021 |
| ITA | Italy — Serie A | 27 | 0.964 | 0.959 |
| GRE | Greece — Super League | 21 | 0.958 | 0.983 |
| POR | Portugal — Primeira Liga | 27 | 0.953 | 0.995 |

## The strongest clubs on the unified scale

| Club | Country | Attack | Defence |
|:--|:--|--:|--:|
| Bayern Munich | GER | 2.031 | 0.716 |
| PSV Eindhoven | NED | 1.899 | 0.869 |
| Barcelona | ESP | 1.848 | 0.753 |
| Paris SG | FRA | 1.722 | 0.696 |
| Sp Lisbon | POR | 1.683 | 0.672 |
| Inter | ITA | 1.639 | 0.702 |
| Real Madrid | ESP | 1.611 | 0.701 |
| Benfica | POR | 1.603 | 0.666 |
| Fenerbahce | TUR | 1.560 | 0.816 |
| Galatasaray | TUR | 1.547 | 0.750 |
| Man City | ENG | 1.545 | 0.657 |
| Celtic | SCO | 1.535 | 0.747 |

Read that ordering with care. PSV Eindhoven, Sporting, Benfica, Fenerbahce, Galatasaray and Celtic all sit above Real Madrid and Manchester City, which is not a credible European power ranking. A club that dominates a weak domestic league scores heavily against weak opposition, and the 701 European ties correct that only partly: most of a club's matches are domestic, so most of its rating is. The bridge is strong enough to carry club-level information out of sample — that is what the test above measures — and not strong enough to make the attack column a ranking. A Champions League price built on it should expect the weak-league sides to be overrated.


## Who cannot be rated

1584 club appearances belong to countries Football-Data does not publish. Those clubs stay unrated, and the model refuses to price a club it has no rating for, so their ties are declined rather than guessed at.

| Country | Appearances |
|:--|--:|
| CZE | 144 |
| AUT | 138 |
| UKR | 104 |
| DEN | 98 |
| NOR | 92 |
| SUI | 90 |
| SRB | 80 |
| CYP | 80 |
| ISR | 66 |
| POL | 60 |
| RUS | 58 |
| CRO | 56 |
