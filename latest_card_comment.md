## Sunday 11 October, 15:26 UTC — scheduled run

Selections changed: 3 added, 9 dropped, 2 moved section.

Provider quota: 94094 (about 94 days at the observed burn)

Markets: **total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5** (excluded: 1x2)

### Best bets

| Match | Market | Selection | Tier | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|
| Coventry v Newcastle | `corners_total_9_5` | over | C | +5.6% | -110 | FanDuel | 0.1 |
| Coventry v Newcastle | `corners_total_10_5` | over | C | +5.3% | +150 | FanDuel | 0.1 |

### Leans

_None._

### What changed

- **Added:** Coventry v Newcastle total_2_5 over
- **Added:** Coventry v Newcastle total_2_5 under
- **Added:** Liverpool v Man City total_2_5 over
- **Dropped:** Crystal Palace v Nott'm Forest corners_1x2 home
- **Dropped:** Crystal Palace v Nott'm Forest corners_total_10_5 over
- **Dropped:** Crystal Palace v Nott'm Forest corners_total_9_5 over
- **Dropped:** Crystal Palace v Nott'm Forest total_2_5 over
- **Dropped:** Hull v Everton corners_1x2 home
- **Dropped:** Hull v Everton corners_total_10_5 over
- **Dropped:** Hull v Everton corners_total_9_5 over
- **Dropped:** Hull v Everton double_chance home_or_draw
- **Dropped:** Hull v Everton draw_no_bet home
- **Moved section:** Liverpool v Man City corners_1x2 home
- **Moved section:** Liverpool v Man City draw_no_bet away


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at 0.1 units for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

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
| Lens v Sp Lisbon | `draw_no_bet` | away | +6.4% | +100 | FanDuel | 0.1 |
| Roma v Real Madrid | `double_chance` | home_or_draw | +6.1% | -109 | BetRivers | 0.1 |
| Arsenal v Lille | `corners_total_10_5` | under | +5.9% | -130 | BetRivers | 0.1 |
| Inter v Club Brugge | `btts` | yes | +5.8% | -120 | DraftKings | 0.1 |

- 6 fixture(s) left out because a club has no rating in the pool: Bodø/Glimt v Dortmund, LASK v Liverpool, Sabah FK v Slavia Praha, Shakhtar Donetsk v AEK, Viking FK v Bayern Munich, ŠK Slovan Bratislava v Stuttgart.
- 14 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### UEFA Europa League

Same European ratings as the Champions League, and **thinner in both directions**: more clubs come from countries with no domestic feed, so more fixtures are declined, and the ones that are priced rest on a scale calibrated mostly by Champions League ties.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Rennes v OFI Crete | `btts` | yes | +6.2% | -102 | FanDuel | 0.1 |
| St. Gilloise v Sociedad | `btts` | no | +5.5% | +138 | FanDuel | 0.1 |
| Benfica v Celtic | `btts` | yes | +5.5% | -108 | FanDuel | 0.1 |

- 18 fixture(s) dropped as already kicked off: AC Milan v Benfica, Anderlecht v Lyon, Bayer Leverkusen v NK Celje, Besiktas JK v Marseille, Celtic v Ferencváros TC, Crystal Palace v Lech Poznań, and 12 more.
- 14 fixture(s) left out because a club has no rating in the pool: AZ Alkmaar v Hapoel Be'er Sheva, Bournemouth v SK Sturm Graz, Celta Vigo v Juventus, Dinamo Zagreb v Anderlecht, Ferencváros TC v Viktoria Plzeň, Jagiellonia Białystok v FC Ararat-Armenia, Lech Poznań v Leverkusen, Marseille v Olympiakos Piraeus, NEC Nijmegen v PFC Levski Sofia, NK Celje v Omonoia FC, Salzburg v AC Milan, Sparta Prague v Lillestrom, TSG Hoffenheim v Besiktas JK, Torreense v Sunderland.

_Fitted but not bet: UEFA Nations League (0 of 0 fixtures rateable), UEFA Europa Conference League (0 of 18 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._

### How the recommendations have done

- Settled: **84** selections, 40 won, 5 returned the stake
- Staked: 11.25 units
- Profit: **+0.53 units** (+4.8% on turnover)
- Still pending: 4
- Played, waiting on results data: **17** — these are settled matches the results feed has not caught up with, so the record above is behind rather than still accumulating.

- Stake returned (void): 5 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 9 staked selection(s) from that section are recorded and not yet scored — nothing settles them. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/38151068352)
