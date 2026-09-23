## Wednesday 23 September, 05:54 UTC — manual run

Selections changed: 5 added, 6 dropped, 1 moved section.

_This run was started by hand, not by the schedule. If you did not start it, someone was testing._

Provider quota: 1104582 (about 17815 more runs)

Markets: **total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5** (excluded: 1x2)

### Best bets

| Match | Market | Selection | Tier | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|
| Aston Villa v Brentford | `corners_1x2` | home | C | +6.9% | -140 | Fanatics | 0.1 |
| Sunderland v Brighton | `corners_total_10_5` | under | C | +5.7% | -148 | BetRivers | 0.1 |
| Arsenal v Leeds | `corners_total_10_5` | under | C | +5.5% | -141 | BetRivers | 0.1 |
| Hull v Everton | `corners_total_10_5` | over | C | +6.8% | +165 | BetRivers | 0.1 |
| Hull v Everton | `corners_total_9_5` | over | C | +4.9% | +105 | BetRivers | 0.1 |
| Man United v Tottenham | `corners_1x2` | away | C | +5.5% | +210 | Fanatics | 0.1 |
| Arsenal v Leeds | `corners_total_9_5` | under | C | +4.9% | +115 | Fanatics | 0.1 |
| Sunderland v Brighton | `corners_total_9_5` | under | C | +4.2% | +105 | BetRivers | 0.1 |

### Leans

_None._

### What changed

- **Added:** Arsenal v Leeds corners_total_9_5 under
- **Added:** Arsenal v Leeds double_chance draw_or_away
- **Added:** Arsenal v Leeds draw_no_bet away
- **Added:** Aston Villa v Brentford draw_no_bet away
- **Added:** Coventry v Newcastle double_chance home_or_away
- **Dropped:** Aston Villa v Brentford total_2_5 over
- **Dropped:** Coventry v Newcastle corners_1x2 home
- **Dropped:** Coventry v Newcastle corners_total_9_5 over
- **Dropped:** Crystal Palace v Nott'm Forest btts yes
- **Dropped:** Hull v Everton double_chance home_or_draw
- **Dropped:** Ipswich v Fulham double_chance home_or_away
- **Moved section:** Hull v Everton draw_no_bet home


## Beyond the Premier League

Neither competition below has been shown to beat a price, and the EFL Cup has been shown not to. They are staked at 0.1 units for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### UEFA Nations League

National teams, on a pool that shares no information with the club ratings — a country has never played any club in them, so nothing bridges the two and this is a second model. It **cannot be backtested**: the free results archive carries no prices, and Football-Data ships closing odds beside every club result, which is how the EFL got a 10,000-bet answer in a weekend. This one can only be judged forward, at roughly 80 matches a year. Two expected problems measured out **not** to apply here — the seeding keeps League A away from League D, so 0.3% of fixtures have a favourite above 90% and none above 95%, and a team's rating survives squad turnover (r = +0.82 across seven years). One applies and cannot be fixed: **5.2% of these matches are at neutral venues and the price feed does not say which**, so those are priced with a home advantage worth about half a goal that one side does not have. The provider quotes all eight card markets here — the only competition outside the Champions League that does — but the results archive carries no corner counts, so **the three corner markets are priced by nobody and cannot be bet**. And treat a large edge here as a large model error first: the first run offered Liechtenstein v Lithuania under 2.5 at +18.9%, calling it 76.6% against a market at 57.6%, when only 47.3% of Liechtenstein's 110 matches since 2014 went under. This card selects on the biggest disagreements, which is where a model is most often simply wrong.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Liechtenstein v Lithuania | `total_2_5` | under | +8.0% | -136 | BetRivers | 0.1 |
| England v Spain | `btts` | no | +6.7% | +110 | BetRivers | 0.1 |
| Turkey v France | `double_chance` | home_or_draw | +6.5% | +150 | BetRivers | 0.1 |
| Romania v Bosnia and Herzegovina | `btts` | no | +6.3% | -107 | BetRivers | 0.1 |

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

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/35824171667)
