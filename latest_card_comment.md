## Sunday 22 November, 17:01 UTC — scheduled run

Selections changed: 27 dropped.

Provider quota: 4922131 (about 1367 days at the observed burn)

Markets: **1x2, total_2_5, btts, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5, team_total_home_2_5, team_total_away_0_5, team_total_away_1_5, team_total_away_2_5** (excluded: double_chance, team_total_home_0_5, team_total_home_1_5)

### Best bets

_None._

### Leans

_None._

### Player props

- Brentford v Everton — **Vitaly Janelt** `player_shots` Over@1.5 at +410 (FanDuel), bet down to +382, 0.6u

_Props carry the smallest stake the card uses: the standing measurement demonstrates no edge, and books reprice on the team sheet after this card is built._

### What changed

- **Dropped:** Brentford v Everton team_total_home_1_5 under
- **Dropped:** Hull v Brighton team_total_away_1_5 under
- **Dropped:** Liverpool v Man United team_total_home_2_5 over


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at the card's base size (1u, or to win 1u on a minus price; the ladder from +200) for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### UEFA Nations League

National teams, on a pool that shares no information with the club ratings — a country has never played any club in them, so nothing bridges the two and this is a second model. It **cannot be backtested**: no free archive carries international prices, so it can only be judged forward, at roughly 80 matches a year. **Only the result markets are bet here.** Measured against the de-vigged market across 45 live fixtures, the model put the chance of over 2.5 goals at 0.418 where the market said 0.499 — eight points low, the same way on every fixture — so `total_2_5` and `btts` are priced by a standing gap rather than by the fixture, and are withheld. Three of the first four selections this section ever made were low-scoring bets off that gap. The baselines are now this competition's own rather than the pool's, which halved a separate bias: it was applying +0.656 goals of home advantage where the Nations League's own is +0.346. Two expected problems measured out **not** to apply — seeding keeps League A away from League D, so 0.3% of fixtures have a favourite above 90% and none above 95%, and a rating survives squad turnover (r = +0.82 across seven years). One remains and cannot be fixed from the feed: 5.2% of these matches are at neutral venues and the price feed does not say which, so those carry a home advantage one side does not have.

| Match | Market | Selection | Bet down to | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|--:|:--|--:|
| Spain v France | `draw_no_bet` | home | -160 | +6.7% | -160 | BetMGM | 1.6 |

- 156 fixture(s) dropped as already kicked off: Albania v Belarus, Albania v Finland, Albania v San Marino, Andorra v Gibraltar, Andorra v Malta, Armenia v Cyprus, and 150 more.
- `btts` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- `total_2_5` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- Ratings include no result after 2026-11-17; the results archive runs about a month behind, so the current international window is not in the fit.
- No corner model: the pool carries no corner counts.

### UEFA Champions League

Priced on the European ratings, where 868 European ties bridge eleven leagues onto one scale — 7.45% better than a league-average prior on held-out ties. That scale **overrates clubs who dominate weak leagues**, and those are the clubs it will most often call value.

| Match | Market | Selection | Bet down to | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|--:|:--|--:|
| Como v AEK | `total_2_5` | under | +159 | +7.8% | +225 | FanDuel | 0.6 |
| Feyenoord v Porto | `corners_1x2` | home | -123 | +7.3% | -106 | BetRivers | 1.06 |
| Arsenal v Dortmund | `draw_no_bet` | away | +423 | +7.0% | +540 | FanDuel | 0.4 |
| Arsenal v Dortmund | `double_chance` | draw_or_away | +174 | +6.7% | +200 | FanDuel | 0.6 |

- 54 fixture(s) dropped as already kicked off: AEK Athens v Real Madrid, AS Roma v Real Madrid, AS Roma v ŠK Slovan Bratislava, Arsenal v Lille, Aston Villa v Fenerbahce, Aston Villa v Viking FK, and 48 more.
- 6 fixture(s) left out because a club has no rating in the pool: Ath Madrid v Viking FK, Bodø/Glimt v LASK, Sabah FK v Barcelona, Shakhtar Donetsk v Fenerbahce, Slavia Praha v Villarreal, ŠK Slovan Bratislava v Betis.
- 26 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### UEFA Europa League

Same European ratings as the Champions League, and **thinner in both directions**: more clubs come from countries with no domestic feed, so more fixtures are declined, and the ones that are priced rest on a scale calibrated mostly by Champions League ties.

| Match | Market | Selection | Bet down to | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|--:|:--|--:|
| OFI Crete v Anderlecht | `double_chance` | home_or_draw | -124 | +6.5% | -110 | DraftKings | 1.1 |

- 71 fixture(s) dropped as already kicked off: AC Milan v Benfica, AC Milan v Ferencváros TC, AZ Alkmaar v Hapoel Be'er Sheva, AZ Alkmaar v Juventus, Anderlecht v Lyon, Anderlecht v Salzburg, and 65 more.
- 1 fixture(s) dropped because their kickoff could not be confirmed from the feed: Rennes v Olympiakos Piraeus.
- 16 fixture(s) left out because a club has no rating in the pool: Besiktas JK v Hapoel Be'er Sheva, Celta Vigo v Bournemouth, Dinamo Zagreb v Leverkusen, Ferencváros TC v NK Celje, Juventus v Omonoia FC, Lyon v Lillestrom, Marseille v PFC Levski Sofia, NEC Nijmegen v Rennes, Olympiakos Piraeus v AC Milan, Salzburg v FC Ararat-Armenia, Sparta Prague v AZ Alkmaar, St. Gilloise v Lech Poznań, Sunderland v Jagiellonia Białystok, TSG Hoffenheim v SK Sturm Graz, Torreense v Celtic, Viktoria Plzeň v Benfica.

_Fitted but not bet: EFL Cup (Carabao) (0 of 0 fixtures rateable), UEFA Europa Conference League (0 of 18 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._


### Due List · goals and assists

Context only: no units, nothing here is a selection, and no edge is shown.

**Anytime goalscorer, over 0.5.** Listed: 10+ Premier League goals last season and a run of league appearances without a goal at the bar his total sets (20+ goals -> 4, 15-19 goals -> 6, 10-14 goals -> 8 straight games).

**Being due has meant scoring less often, not more.** Seasons 2022/23 to 2025/26: listed players had a goal in 18.7% of 380 next appearances, against 28.8% for the same qualifiers when not due (n = 2,270; difference -10.2%, 95% -14.5% to -5.8%). No price-based measurement exists: historical player-prop prices were never bought.

| Player | Team | Opp | Kickoff (UTC) | Last season | Drought (bar) | 1 in N for him | Status | Price |
|:--|:--|:--|:--|--:|:--|--:|:--|:--|
| Danny Welbeck | Chelsea | Nottingham Forest | 2026-11-27 20:00 | 13 goals, 27% of apps | 13 (8) | 1 in 60 | — | not posted |
| Morgan Gibbs-White | Nottingham Forest | Chelsea | 2026-11-27 20:00 | 15 goals, 35% of apps | 8 (6) | 1 in 32 | — | not posted |

**1+ assist, over 0.5.** Listed: 7+ Premier League assists last season and a run of league appearances without an assist at the bar his total sets (12+ assists -> 8, 9-11 assists -> 10, 7-8 assists -> 13 straight games).

**Being due has meant assisting less often, not more.** Seasons 2022/23 to 2025/26: listed players had an assist in 10.3% of 448 next appearances, against 17.8% for the same qualifiers when not due (n = 2,484; difference -7.5%, 95% -10.7% to -4.3%). No price-based measurement exists: historical player-prop prices were never bought.

| Player | Team | Opp | Kickoff (UTC) | Last season | Drought (bar) | 1 in N for him | Status | Price |
|:--|:--|:--|:--|--:|:--|--:|:--|:--|
| James Garner | Everton | Brentford | 2026-11-23 20:00 | 7 assists, 18% of apps | 13 (13) | 1 in 14 | — | +460 (FanDuel) |

### How the recommendations have done

- Settled: **193** selections, 81 won, 8 returned the stake
- Staked: 196.18 units
- Profit: **-1.33 units** (-0.7% on turnover)
- Still pending: 2
- Played, waiting on results data: **2** — these are settled matches the results feed has not caught up with, so the record above is behind rather than still accumulating.

- Stake returned (void): 8 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 6 staked selection(s) from that section are on this card. It is graded on a record of its own (`beyond_record.md`): 92 settled, 34 won, 6 returned the stake, -7.52 units. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

### Closing-line check by market

Consensus CLV on each market's picks, judged once it has 50 with a closing price. Cutting or raising a market is your call; this says where the evidence points.

- `corners_1x2`: 22 of 50 picks needed, not judged yet.
- `corners_total_9_5`: 19 of 50 picks needed, not judged yet.
- `corners_total_10_5`: 18 of 50 picks needed, not judged yet.
- `draw_no_bet`: 18 of 50 picks needed, not judged yet.
- `team_total_away_1_5`: 16 of 50 picks needed, not judged yet.
- `team_total_home_1_5`: 14 of 50 picks needed, not judged yet.
- `1x2`: 13 of 50 picks needed, not judged yet.
- `double_chance`: 11 of 50 picks needed, not judged yet.
- `btts`: 4 of 50 picks needed, not judged yet.
- `team_total_away_0_5`: 3 of 50 picks needed, not judged yet.
- `team_total_home_2_5`: 2 of 50 picks needed, not judged yet.
- `total_2_5`: 2 of 50 picks needed, not judged yet.
- `team_total_away_2_5`: 1 of 50 picks needed, not judged yet.
- `team_total_home_0_5`: 1 of 50 picks needed, not judged yet.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/45046592926)
