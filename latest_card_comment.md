## Sunday 04 October, 14:43 UTC — scheduled run

Already sent today; same selections (1 price move(s)).

Provider quota: **10955** — about 10 day(s) at the observed burn. **Top this up or the schedule stops.**

Markets: **total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5** (excluded: 1x2)

### Best bets

| Match | Market | Selection | Tier | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|
| Arsenal v Leeds | `corners_total_10_5` | under | C | +7.6% | -129 | Caesars | 0.1 |
| Sunderland v Brighton | `corners_total_10_5` | under | C | +6.9% | -141 | BetRivers | 0.1 |
| Hull v Everton | `corners_total_10_5` | over | C | +6.8% | +165 | BetRivers | 0.1 |
| Chelsea v Bournemouth | `draw_no_bet` | away | C | +6.6% | +240 | FanDuel | 0.1 |
| Hull v Everton | `corners_total_9_5` | over | C | +5.7% | +111 | Caesars | 0.1 |
| Sunderland v Brighton | `corners_total_9_5` | under | C | +5.2% | +110 | BetRivers | 0.1 |
| Arsenal v Leeds | `corners_total_9_5` | under | C | +4.3% | +112 | BetRivers | 0.1 |

### Leans

_None._


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at 0.1 units for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### UEFA Nations League

National teams, on a pool that shares no information with the club ratings — a country has never played any club in them, so nothing bridges the two and this is a second model. It **cannot be backtested**: no free archive carries international prices, so it can only be judged forward, at roughly 80 matches a year. **Only the result markets are bet here.** Measured against the de-vigged market across 45 live fixtures, the model put the chance of over 2.5 goals at 0.418 where the market said 0.499 — eight points low, the same way on every fixture — so `total_2_5` and `btts` are priced by a standing gap rather than by the fixture, and are withheld. Three of the first four selections this section ever made were low-scoring bets off that gap. The baselines are now this competition's own rather than the pool's, which halved a separate bias: it was applying +0.656 goals of home advantage where the Nations League's own is +0.346. Two expected problems measured out **not** to apply — seeding keeps League A away from League D, so 0.3% of fixtures have a favourite above 90% and none above 95%, and a rating survives squad turnover (r = +0.82 across seven years). One remains and cannot be fixed from the feed: 5.2% of these matches are at neutral venues and the price feed does not say which, so those carry a home advantage one side does not have.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| England v Czech Republic | `double_chance` | draw_or_away | +7.0% | +330 | BetRivers | 0.1 |
| Scotland v Slovenia | `double_chance` | draw_or_away | +6.9% | +104 | BetRivers | 0.1 |
| Belarus v Finland | `draw_no_bet` | home | +6.7% | +140 | BetMGM | 0.1 |
| Ukraine v Hungary | `draw_no_bet` | home | +5.8% | -135 | DraftKings | 0.1 |

- 85 fixture(s) dropped as already kicked off: Albania v Belarus, Andorra v Malta, Armenia v Latvia, Armenia v Montenegro, Austria v Israel, Austria v Kosovo, and 79 more.
- `btts` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- `total_2_5` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- Ratings include no result after 2026-08-26; the results archive runs about a month behind, so the current international window is not in the fit.
- No corner model: the pool carries no corner counts.
- 9 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### EFL Cup (Carabao)

Priced on the unified English ratings. Measured out of sample, a club's rating does **not** survive a division change — carrying it across is worse than calling the club average for its new division. What transfers is the division, which the market also knows.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Fulham v Crystal Palace | `btts` | no | +4.5% | +125 | BetMGM | 0.1 |
| Fulham v Crystal Palace | `total_2_5` | under | +2.4% | +115 | Bovada | 0.1 |

- 10 fixture(s) dropped as already kicked off: Coventry v Aston Villa, Everton v Wolves, Fleetwood Town v Sheffield United, Ipswich v Arsenal, Liverpool v Tottenham, Man City v Norwich, and 4 more.
- 1 fixture(s) left out because a club has no rating in the pool: Bradford City v Peterborough United.

### UEFA Champions League

Priced on the European ratings, where 868 European ties bridge eleven leagues onto one scale — 7.45% better than a league-average prior on held-out ties. That scale **overrates clubs who dominate weak leagues**, and those are the clubs it will most often call value.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Arsenal v Lille | `total_2_5` | under | +7.0% | +150 | BetUS | 0.1 |
| Arsenal v Lille | `corners_total_10_5` | under | +7.0% | -121 | BetRivers | 0.1 |
| Ath Madrid v Man United | `draw_no_bet` | home | +6.5% | -136 | FanDuel | 0.1 |
| Inter v Club Brugge | `corners_1x2` | away | +6.5% | +480 | BetRivers | 0.1 |

- 6 fixture(s) left out because a club has no rating in the pool: Bodø/Glimt v Dortmund, LASK v Liverpool, Sabah FK v Slavia Praha, Shakhtar Donetsk v AEK, Viking FK v Bayern Munich, ŠK Slovan Bratislava v Stuttgart.
- 16 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### UEFA Europa League

Same European ratings as the Champions League, and **thinner in both directions**: more clubs come from countries with no domestic feed, so more fixtures are declined, and the ones that are priced rest on a scale calibrated mostly by Champions League ties.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Rennes v OFI Crete | `double_chance` | draw_or_away | +6.4% | +220 | FanDuel | 0.1 |
| Benfica v Celtic | `btts` | yes | +5.7% | -106 | FanDuel | 0.1 |
| Rennes v OFI Crete | `btts` | yes | +5.0% | -112 | FanDuel | 0.1 |
| St. Gilloise v Sociedad | `btts` | no | +4.8% | +130 | FanDuel | 0.1 |

- 18 fixture(s) dropped as already kicked off: AC Milan v Benfica, Anderlecht v Lyon, Bayer Leverkusen v NK Celje, Besiktas JK v Marseille, Celtic v Ferencváros TC, Crystal Palace v Lech Poznań, and 12 more.
- 14 fixture(s) left out because a club has no rating in the pool: AZ Alkmaar v Hapoel Be'er Sheva, Bournemouth v SK Sturm Graz, Celta Vigo v Juventus, Dinamo Zagreb v Anderlecht, Ferencváros TC v Viktoria Plzeň, Jagiellonia Białystok v FC Ararat-Armenia, Lech Poznań v Leverkusen, Marseille v Olympiakos Piraeus, NEC Nijmegen v PFC Levski Sofia, NK Celje v Omonoia FC, Salzburg v AC Milan, Sparta Prague v Lillestrom, TSG Hoffenheim v Besiktas JK, Torreense v Sunderland.

_Fitted but not bet: UEFA Europa Conference League (0 of 18 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._

### How the recommendations have done

- Settled: **84** selections, 40 won, 5 returned the stake
- Staked: 11.25 units
- Profit: **+0.53 units** (+4.8% on turnover)
- Still pending: 11

- Stake returned (void): 5 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 14 staked selection(s) from that section are recorded and not yet scored — nothing settles them. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/37210133547)
