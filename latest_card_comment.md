## Saturday 28 November, 17:26 UTC — scheduled run

Selections changed: 4 added, 16 dropped, 2 moved section.

Provider quota: 4879066 (about 1355 days at the observed burn)

Markets: **1x2, total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5, team_total_home_0_5, team_total_home_1_5, team_total_home_2_5, team_total_away_0_5, team_total_away_1_5, team_total_away_2_5** (excluded: none)

### Best bets

| Match | Market | Selection | Tier | Bet down to | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|------------:|-----:|------:|:-----|------:|
| Fulham v Bournemouth | `corners_1x2` | home | C | -107 | +5.1% | +100 | FanDuel | 1.0 |
| Crystal Palace v Hull | `team_total_home_1_5` | under | C | -108 | +5.0% | -102 | Bovada | 1.02 |
| Sunderland v Tottenham | `1x2` | away | C | -101 | +5.0% | +105 | BetMGM | 1.0 |
| Brighton v Newcastle | `corners_1x2` | away | C | +301 | +4.6% | +320 | DraftKings | 0.6 |
| Arsenal v Man City | `corners_1x2` | away | C | +149 | +3.6% | +150 | FanDuel | 1.0 |

### Leans

_None._

_Priced but not on the fixture slate yet, so not rated on this card: Coventry v Ipswich (2026-12-01), Aston Villa v Everton (2026-12-02), Bournemouth v Brighton (2026-12-02), Brentford v Arsenal (2026-12-02), Chelsea v Crystal Palace (2026-12-02), Hull v Nott'm Forest (2026-12-02), Liverpool v Sunderland (2026-12-02), Man City v Leeds (2026-12-02), Newcastle v Man United (2026-12-02), Tottenham v Fulham (2026-12-03). They return once the fixtures feed lists them._

### Player props

- Ipswich v Aston Villa — **Matty Cash** `player_to_receive_card` Yes at +390 (DraftKings), bet down to +275, 0.6u
- Arsenal v Man City — **Noni Madueke** `player_to_receive_card` Yes at +700 (DraftKings), bet down to +537, 0.4u
- Brentford v Arsenal — **Vitaly Janelt** `player_goal_scorer_anytime` Yes at +1400 (Fanatics), bet down to +913, 0.4u
- Chelsea v Crystal Palace — **Jordan Henderson** `player_goal_scorer_anytime` Yes at +1050 (Fanatics), bet down to +753, 0.4u
- Fulham v Bournemouth — **Sander Berge** `player_shots` Over@0.5 at +105 (BetRivers), bet down to -107, 1.0u
- Crystal Palace v Hull — **Hull goalkeeper** `player_goalie_saves_alternate` Over@3.5 at +105 (DraftKings), bet down to -106, 1.0u
- Ipswich v Aston Villa — **Sasa Lukic** `player_shots` Over@0.5 at +105 (BetRivers), bet down to -105, 1.0u
- Arsenal v Man City — **Declan Rice** `player_shots` Over@1.5 at +280 (BetRivers), bet down to +248, 0.6u
- Sunderland v Tottenham — **Noah Sadiki** `player_shots_on_target` Over@0.5 at +400 (BetRivers), bet down to +351, 0.6u
- Everton v Liverpool — **Harrison Armstrong** `player_shots` Over@1.5 at +330 (BetRivers), bet down to +301, 0.6u
- Brighton v Newcastle — **Jacob Murphy** `player_to_receive_card` Yes at +650 (DraftKings), bet down to +591, 0.4u

_Props carry the smallest stake the card uses: the standing measurement demonstrates no edge, and books reprice on the team sheet after this card is built._

### What changed

- **Dropped:** Leeds v Coventry team_total_home_1_5 under
- **Dropped:** Man United v Brentford 1x2 away
- **Added:** Fulham v Bournemouth corners_1x2 home
- **Dropped:** Fulham v Bournemouth corners_total_10_5 over


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at the card's base size (1u, or to win 1u on a minus price; the ladder from +200) for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### UEFA Nations League

National teams, on a pool that shares no information with the club ratings — a country has never played any club in them, so nothing bridges the two and this is a second model. It **cannot be backtested**: no free archive carries international prices, so it can only be judged forward, at roughly 80 matches a year. **Only the result markets are bet here.** Measured against the de-vigged market across 45 live fixtures, the model put the chance of over 2.5 goals at 0.418 where the market said 0.499 — eight points low, the same way on every fixture — so `total_2_5` and `btts` are priced by a standing gap rather than by the fixture, and are withheld. Three of the first four selections this section ever made were low-scoring bets off that gap. The baselines are now this competition's own rather than the pool's, which halved a separate bias: it was applying +0.656 goals of home advantage where the Nations League's own is +0.346. Two expected problems measured out **not** to apply — seeding keeps League A away from League D, so 0.3% of fixtures have a favourite above 90% and none above 95%, and a rating survives squad turnover (r = +0.82 across seven years). One remains and cannot be fixed from the feed: 5.2% of these matches are at neutral venues and the price feed does not say which, so those carry a home advantage one side does not have.

| Match | Market | Selection | Bet down to | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|--:|:--|--:|
| Spain v France | `draw_no_bet` | home | -160 | +6.7% | -160 | BetMGM | 1.6 |
| Slovenia v Wales | `draw_no_bet` | home | -127 | +5.3% | -118 | BetMGM | 1.18 |
| Republic of Ireland v Croatia | `double_chance` | home_or_draw | -130 | +4.7% | -124 | BetRivers | 1.24 |
| Republic of Ireland v Croatia | `draw_no_bet` | home | +187 | +4.5% | +195 | BetMGM | 1.0 |

- 156 fixture(s) dropped as already kicked off: Albania v Belarus, Albania v Finland, Albania v San Marino, Andorra v Gibraltar, Andorra v Malta, Armenia v Cyprus, and 150 more.
- `btts` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- `total_2_5` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- Ratings include no result after 2026-11-17; the results archive runs about a month behind, so the current international window is not in the fit.
- No corner model: the pool carries no corner counts.
- 1 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### UEFA Champions League

Priced on the European ratings, where 868 European ties bridge eleven leagues onto one scale — 7.45% better than a league-average prior on held-out ties. That scale **overrates clubs who dominate weak leagues**, and those are the clubs it will most often call value.

| Match | Market | Selection | Bet down to | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|--:|:--|--:|
| Stuttgart v Lille | `corners_1x2` | away | +187 | +7.0% | +220 | BetRivers | 0.6 |
| Stuttgart v Lille | `btts` | no | +151 | +6.4% | +164 | FanDuel | 1.0 |
| Betis v Como | `btts` | no | +158 | +6.2% | +170 | FanDuel | 1.0 |
| Man United v RB Leipzig | `double_chance` | draw_or_away | -105 | +6.2% | +106 | BetRivers | 1.0 |

- 72 fixture(s) dropped as already kicked off: AEK Athens v Real Madrid, AS Roma v Real Madrid, AS Roma v ŠK Slovan Bratislava, Arsenal v Borussia Dortmund, Arsenal v Lille, Aston Villa v Fenerbahce, and 66 more.
- 6 fixture(s) left out because a club has no rating in the pool: Bayern Munich v Slavia Praha, LASK v Fenerbahce, Lens v Bodø/Glimt, Viking FK v Feyenoord, Villarreal v Sabah FK, ŠK Slovan Bratislava v Shakhtar Donetsk.
- 16 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### UEFA Europa League

Same European ratings as the Champions League, and **thinner in both directions**: more clubs come from countries with no domestic feed, so more fixtures are declined, and the ones that are priced rest on a scale calibrated mostly by Champions League ties.

| Match | Market | Selection | Bet down to | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|--:|:--|--:|
| Benfica v OFI Crete | `total_2_5` | under | +256 | +1.8% | +280 | FanDuel | 0.6 |
| Lyon v St. Gilloise | `total_2_5` | under | -102 | +1.5% | +104 | FanDuel | 1.0 |

- 89 fixture(s) dropped as already kicked off: AC Milan v Benfica, AC Milan v Ferencváros TC, AZ Alkmaar v Hapoel Be'er Sheva, AZ Alkmaar v Juventus, Anderlecht v Lyon, Anderlecht v Salzburg, and 83 more.
- 1 fixture(s) dropped because their kickoff could not be confirmed from the feed: Rennes v Olympiakos Piraeus.
- 16 fixture(s) left out because a club has no rating in the pool: AC Milan v Sunderland, AZ Alkmaar v SK Sturm Graz, Anderlecht v TSG Hoffenheim, Bournemouth v Viktoria Plzeň, FC Ararat-Armenia v NEC Nijmegen, Hapoel Be'er Sheva v Juventus, Jagiellonia Białystok v Crystal Palace, Lech Poznań v Ferencváros TC, Leverkusen v Besiktas JK, Marseille v Celta Vigo, NK Celje v Olympiakos Piraeus, Omonoia FC v Celtic, PFC Levski Sofia v Lillestrom, Rennes v Dinamo Zagreb, Salzburg v Sparta Prague, Sociedad v Torreense.

_Fitted but not bet: EFL Cup (Carabao) (0 of 0 fixtures rateable), UEFA Europa Conference League (0 of 17 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._


### Due List · goals and assists

Context only: no units, nothing here is a selection, and no edge is shown.

**Anytime goalscorer, over 0.5.** Listed: 10+ Premier League goals last season and a run of league appearances without a goal at the bar his total sets (20+ goals -> 4, 15-19 goals -> 6, 10-14 goals -> 8 straight games).

**Being due has meant scoring less often, not more.** Seasons 2022/23 to 2025/26: listed players had a goal in 18.7% of 380 next appearances, against 28.8% for the same qualifiers when not due (n = 2,270; difference -10.2%, 95% -14.5% to -5.8%). No price-based measurement exists: historical player-prop prices were never bought.

| Player | Team | Opp | Kickoff (UTC) | Last season | Drought (bar) | 1 in N for him | Status | Price |
|:--|:--|:--|:--|--:|:--|--:|:--|:--|
| Harry Wilson | Leeds United | Manchester City | 2026-12-02 19:30 | 10 goals, 28% of apps | 16 (8) | 1 in 183 | — | not posted |
| Danny Welbeck | Chelsea | Crystal Palace | 2026-12-02 19:30 | 13 goals, 27% of apps | 14 (8) | 1 in 82 | — | +150 (Fanatics) |
| Viktor Gyökeres | Arsenal | Manchester City | 2026-11-29 16:30 | 14 goals, 28% of apps | 11 (8) | 1 in 36 | — | +240 (DraftKings) |

**1+ assist, over 0.5.** Listed: 7+ Premier League assists last season and a run of league appearances without an assist at the bar his total sets (12+ assists -> 8, 9-11 assists -> 10, 7-8 assists -> 13 straight games).

**Being due has meant assisting less often, not more.** Seasons 2022/23 to 2025/26: listed players had an assist in 10.3% of 448 next appearances, against 17.8% for the same qualifiers when not due (n = 2,484; difference -7.5%, 95% -10.7% to -4.3%). No price-based measurement exists: historical player-prop prices were never bought.

| Player | Team | Opp | Kickoff (UTC) | Last season | Drought (bar) | 1 in N for him | Status | Price |
|:--|:--|:--|:--|--:|:--|--:|:--|:--|
| Rayan Cherki | Manchester City | Arsenal | 2026-11-29 16:30 | 12 assists, 27% of apps | 9 (8) | 1 in 18 | — | +280 (FanDuel) |
| James Garner | Everton | Liverpool | 2026-11-29 12:00 | 7 assists, 18% of apps | 14 (13) | 1 in 17 | — | +600 (FanDuel) |

### How the recommendations have done

- Settled: **202** selections, 84 won, 8 returned the stake
- Staked: 204.20 units
- Profit: **-2.24 units** (-1.1% on turnover)
- Still pending: 17

- Stake returned (void): 8 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 10 staked selection(s) from that section are on this card. It is graded on a record of its own (`beyond_record.md`): 113 settled, 43 won, 8 returned the stake, -1.88 units. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

### Closing-line check by market

Consensus CLV on each market's picks, judged once it has 50 with a closing price. Cutting or raising a market is your call; this says where the evidence points.

- `corners_1x2`: 23 of 50 picks needed, not judged yet.
- `corners_total_9_5`: 19 of 50 picks needed, not judged yet.
- `corners_total_10_5`: 18 of 50 picks needed, not judged yet.
- `draw_no_bet`: 18 of 50 picks needed, not judged yet.
- `team_total_away_1_5`: 17 of 50 picks needed, not judged yet.
- `team_total_home_1_5`: 17 of 50 picks needed, not judged yet.
- `1x2`: 14 of 50 picks needed, not judged yet.
- `double_chance`: 11 of 50 picks needed, not judged yet.
- `btts`: 4 of 50 picks needed, not judged yet.
- `team_total_away_0_5`: 3 of 50 picks needed, not judged yet.
- `team_total_home_0_5`: 2 of 50 picks needed, not judged yet.
- `team_total_home_2_5`: 2 of 50 picks needed, not judged yet.
- `total_2_5`: 2 of 50 picks needed, not judged yet.
- `team_total_away_2_5`: 1 of 50 picks needed, not judged yet.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/46169932604)
