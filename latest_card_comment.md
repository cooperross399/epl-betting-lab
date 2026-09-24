## Thursday 24 September, 10:35 UTC — scheduled run

Selections changed: 1 added, 1 dropped.

Provider quota: 1104094 (about 17807 more runs)

Markets: **total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5** (excluded: 1x2)

### Best bets

| Match | Market | Selection | Tier | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|
| Aston Villa v Brentford | `corners_1x2` | home | C | +6.9% | -140 | Fanatics | 0.1 |
| Arsenal v Leeds | `corners_total_10_5` | under | C | +5.5% | -141 | BetRivers | 0.1 |
| Sunderland v Brighton | `corners_total_10_5` | under | C | +5.1% | -152 | BetRivers | 0.1 |
| Hull v Everton | `corners_total_10_5` | over | C | +6.1% | +160 | BetRivers | 0.1 |
| Arsenal v Leeds | `corners_total_9_5` | under | C | +4.9% | +115 | Fanatics | 0.1 |
| Hull v Everton | `corners_total_9_5` | over | C | +4.5% | +102 | BetRivers | 0.1 |
| Sunderland v Brighton | `corners_total_9_5` | under | C | +4.2% | +105 | BetRivers | 0.1 |
| Man United v Tottenham | `corners_1x2` | away | C | +4.6% | +200 | Fanatics | 0.1 |

### Leans

_None._

### What changed

- **Added:** Man United v Tottenham btts no
- **Dropped:** Coventry v Newcastle double_chance draw_or_away


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at 0.1 units for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### UEFA Nations League

National teams, on a pool that shares no information with the club ratings — a country has never played any club in them, so nothing bridges the two and this is a second model. It **cannot be backtested**: no free archive carries international prices, so it can only be judged forward, at roughly 80 matches a year. **Only the result markets are bet here.** Measured against the de-vigged market across 45 live fixtures, the model put the chance of over 2.5 goals at 0.418 where the market said 0.499 — eight points low, the same way on every fixture — so `total_2_5` and `btts` are priced by a standing gap rather than by the fixture, and are withheld. Three of the first four selections this section ever made were low-scoring bets off that gap. The baselines are now this competition's own rather than the pool's, which halved a separate bias: it was applying +0.656 goals of home advantage where the Nations League's own is +0.346. Two expected problems measured out **not** to apply — seeding keeps League A away from League D, so 0.3% of fixtures have a favourite above 90% and none above 95%, and a rating survives squad turnover (r = +0.82 across seven years). One remains and cannot be fixed from the feed: 5.2% of these matches are at neutral venues and the price feed does not say which, so those carry a home advantage one side does not have.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Italy v Belgium | `draw_no_bet` | away | +6.7% | +135 | BetRivers | 0.1 |
| North Macedonia v Switzerland | `draw_no_bet` | home | +6.6% | +440 | BetRivers | 0.1 |
| Sweden v Romania | `double_chance` | draw_or_away | +5.9% | +163 | BetRivers | 0.1 |
| Turkey v France | `draw_no_bet` | home | +5.9% | +350 | BetRivers | 0.1 |

- `btts` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- `total_2_5` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- Ratings include no result after 2026-08-26; the results archive runs about a month behind, so the current international window is not in the fit.
- No corner model: the pool carries no corner counts.

### EFL Cup (Carabao)

Priced on the unified English ratings. Measured out of sample, a club's rating does **not** survive a division change — carrying it across is worse than calling the club average for its new division. What transfers is the division, which the market also knows.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Fleetwood Town v Sheffield United | `total_2_5` | under | +2.8% | +120 | BetRivers | 0.1 |
| Everton v Wolves | `total_2_5` | under | +2.4% | +102 | BetRivers | 0.1 |
| Ipswich v Arsenal | `total_2_5` | under | +0.6% | +130 | BetMGM | 0.1 |

- 2 fixture(s) left out because a club has no rating in the pool: Bradford City v Peterborough United, Peterborough United v Barnsley.

### UEFA Champions League

Priced on the European ratings, where 701 European ties bridge eleven leagues onto one scale — 8.5% better than a league-average prior on held-out ties. That scale **overrates clubs who dominate weak leagues**, and those are the clubs it will most often call value.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Arsenal v Lille | `total_2_5` | under | +7.0% | +150 | BetRivers | 0.1 |
| Arsenal v Lille | `corners_total_10_5` | under | +6.9% | -122 | BetRivers | 0.1 |
| Inter v Club Brugge | `corners_1x2` | away | +6.5% | +480 | BetRivers | 0.1 |
| Roma v Real Madrid | `total_2_5` | under | +6.4% | +210 | FanDuel | 0.1 |

- 6 fixture(s) left out because a club has no rating in the pool: Bodø/Glimt v Dortmund, LASK v Liverpool, Sabah FK v Slavia Praha, Shakhtar Donetsk v AEK, Viking FK v Bayern Munich, ŠK Slovan Bratislava v Stuttgart.

### UEFA Europa League

Same European ratings as the Champions League, and **thinner in both directions**: more clubs come from countries with no domestic feed, so more fixtures are declined, and the ones that are priced rest on a scale calibrated mostly by Champions League ties.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Rennes v OFI Crete | `double_chance` | draw_or_away | +5.9% | +210 | FanDuel | 0.1 |
| Benfica v Celtic | `btts` | yes | +5.7% | -106 | FanDuel | 0.1 |
| Anderlecht v Lyon | `double_chance` | home_or_draw | +5.6% | -135 | DraftKings | 0.1 |
| Anderlecht v Lyon | `draw_no_bet` | home | +5.6% | +144 | FanDuel | 0.1 |

- 29 fixture(s) left out because a club has no rating in the pool: AC Milan v Benfica, AZ Alkmaar v Hapoel Be'er Sheva, Besiktas JK v Marseille, Bournemouth v SK Sturm Graz, Celta Vigo v Juventus, Celtic v Ferencváros TC, Crystal Palace v Lech Poznań, Dinamo Zagreb v Anderlecht, FC Ararat-Armenia v Sparta Prague, Ferencváros TC v Viktoria Plzeň, Hapoel Be'er Sheva v Dinamo Zagreb, Jagiellonia Białystok v FC Ararat-Armenia, Juventus v NEC Nijmegen, Lech Poznań v Leverkusen, Leverkusen v NK Celje, Lillestrom v Torreense, Marseille v Olympiakos Piraeus, NEC Nijmegen v PFC Levski Sofia, NK Celje v Omonoia FC, OFI Crete v TSG Hoffenheim, Olympiakos Piraeus v Jagiellonia Białystok, Omonoia FC v Celta Vigo, PFC Levski Sofia v Salzburg, SK Sturm Graz v Rennes, Salzburg v AC Milan, Sparta Prague v Lillestrom, TSG Hoffenheim v Besiktas JK, Torreense v Sunderland, Viktoria Plzeň v St. Gilloise.

_Fitted but not bet: UEFA Europa Conference League (0 of 18 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._

### How the recommendations have done

- Settled: **79** selections, 40 won
- Staked: 10.75 units
- Profit: **+0.53 units** (+5.0% on turnover)
- Still pending: 9

- Stake returned (void): 5

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/35987714106)
