## Friday 16 October, 12:47 UTC — manual run

Selections changed: 3 added, 2 dropped, 4 moved section.

_This run was started by hand, not by the schedule. If you did not start it, someone was testing._

Provider quota: 77001 (about 77 days at the observed burn)

Markets: **total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5** (excluded: 1x2)

### Best bets

| Match | Market | Selection | Tier | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|
| Bournemouth v Sunderland | `corners_total_9_5` | over | C | +6.6% | +100 | FanDuel | 0.1 |
| Bournemouth v Sunderland | `corners_total_10_5` | over | C | +6.3% | +164 | FanDuel | 0.1 |
| Leeds v Man United | `corners_1x2` | home | C | +5.7% | +120 | DraftKings | 0.1 |
| Tottenham v Coventry | `corners_1x2` | away | C | +5.5% | +360 | FanDuel | 0.1 |
| Fulham v Hull | `corners_1x2` | away | C | +5.2% | +390 | DraftKings | 0.1 |
| Newcastle v Aston Villa | `corners_total_10_5` | over | C | +3.6% | +126 | FanDuel | 0.1 |
| Brighton v Crystal Palace | `draw_no_bet` | away | C | +4.5% | +370 | FanDuel | 0.1 |

### Leans

_None._

### What changed

- **Added:** Leeds v Man United corners_1x2 draw
- **Added:** Nott'm Forest v Arsenal corners_total_10_5 over
- **Added:** Nott'm Forest v Arsenal corners_total_9_5 over
- **Dropped:** Everton v Chelsea corners_1x2 away
- **Dropped:** Man City v Ipswich corners_total_10_5 over
- **Moved section:** Bournemouth v Sunderland corners_total_10_5 over
- **Moved section:** Bournemouth v Sunderland corners_total_9_5 over
- **Moved section:** Brentford v Liverpool corners_total_9_5 over
- **Moved section:** Man City v Ipswich btts yes


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at 0.1 units for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### EFL Cup (Carabao)

Priced on the unified English ratings. Measured out of sample, a club's rating does **not** survive a division change — carrying it across is worse than calling the club average for its new division. What transfers is the division, which the market also knows.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Fulham v Crystal Palace | `btts` | no | +4.8% | +130 | BetMGM | 0.1 |
| Fulham v Crystal Palace | `total_2_5` | under | +2.6% | +118 | Bovada | 0.1 |

- 10 fixture(s) dropped as already kicked off: Coventry v Aston Villa, Everton v Wolves, Fleetwood Town v Sheffield United, Ipswich v Arsenal, Liverpool v Tottenham, Man City v Norwich, and 4 more.
- 1 fixture(s) left out because a club has no rating in the pool: Bradford City v Peterborough United.

_Fitted but not bet: UEFA Nations League (0 of 0 fixtures rateable), UEFA Champions League (0 of 0 fixtures rateable), UEFA Europa League (0 of 0 fixtures rateable), UEFA Europa Conference League (0 of 0 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._

### How the recommendations have done

- Settled: **105** selections, 46 won, 6 returned the stake
- Staked: 13.35 units
- Profit: **-0.16 units** (-1.2% on turnover)
- Still pending: 9

- Stake returned (void): 6 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 2 staked selection(s) from that section are recorded and not yet scored — nothing settles them. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/38902478517)
