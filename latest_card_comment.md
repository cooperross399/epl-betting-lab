## Friday 27 November, 14:18 UTC — scheduled run

Selections changed: 61 added.

Provider quota: 4891894 (about 1358 days at the observed burn)

Markets: **1x2, total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5, team_total_home_0_5, team_total_home_1_5, team_total_home_2_5, team_total_away_0_5, team_total_away_1_5, team_total_away_2_5** (excluded: none)

### Best bets

| Match | Market | Selection | Tier | Bet down to | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|------------:|-----:|------:|:-----|------:|
| Fulham v Bournemouth | `corners_1x2` | home | C | -124 | +5.5% | -115 | BetMGM | 1.15 |
| Crystal Palace v Hull | `team_total_home_1_5` | under | C | -109 | +5.0% | -102 | Bovada | 1.02 |
| Sunderland v Tottenham | `1x2` | away | C | -101 | +5.3% | +107 | BetOnline.ag | 1.0 |
| Man United v Brentford | `team_total_away_1_5` | under | C | -151 | +3.7% | -150 | Bovada | 1.5 |
| Nott'm Forest v Chelsea | `team_total_home_1_5` | over | C | +118 | +5.0% | +125 | Bovada | 1.0 |
| Brighton v Newcastle | `corners_1x2` | away | C | +305 | +4.9% | +330 | DraftKings | 0.6 |
| Leeds v Coventry | `corners_1x2` | away | C | +302 | +4.6% | +320 | DraftKings | 0.6 |
| Arsenal v Man City | `corners_1x2` | away | C | +149 | +3.7% | +150 | FanDuel | 1.0 |

### Leans

_None._

_Priced but not on the fixture slate yet, so not rated on this card: Coventry v Ipswich (2026-12-01), Aston Villa v Everton (2026-12-02), Bournemouth v Brighton (2026-12-02), Brentford v Arsenal (2026-12-02), Chelsea v Crystal Palace (2026-12-02), Hull v Nott'm Forest (2026-12-02), Liverpool v Sunderland (2026-12-02), Man City v Leeds (2026-12-02), Newcastle v Man United (2026-12-02), Tottenham v Fulham (2026-12-03). They return once the fixtures feed lists them._

### Player props

- Leeds v Coventry — **Leeds goalkeeper** `player_goalie_saves_alternate` Over@2.5 at +170 (Bovada), bet down to +116, 1.0u
- Nott'm Forest v Chelsea — **Jordan Henderson** `player_shots` Over@0.5 at +105 (BetRivers), bet down to -124, 1.0u
- Ipswich v Aston Villa — **Matty Cash** `player_to_receive_card` Yes at +390 (DraftKings), bet down to +278, 0.6u
- Arsenal v Man City — **Noni Madueke** `player_to_receive_card` Yes at +700 (DraftKings), bet down to +540, 0.4u
- Fulham v Bournemouth — **Sander Berge** `player_shots` Over@0.5 at +105 (BetRivers), bet down to -106, 1.0u
- Brentford v Arsenal — **Vitaly Janelt** `player_goal_scorer_anytime` Yes at +1100 (Bovada), bet down to +823, 0.4u
- Crystal Palace v Hull — **Hull goalkeeper** `player_goalie_saves_alternate` Over@3.5 at +105 (DraftKings), bet down to -103, 1.0u
- Ipswich v Aston Villa — **Florentino Luis** `player_shots_on_target` Over@0.5 at +400 (BetRivers), bet down to +359, 0.6u
- Everton v Liverpool — **Harrison Armstrong** `player_shots` Over@1.5 at +330 (BetRivers), bet down to +303, 0.6u
- Arsenal v Man City — **Declan Rice** `player_shots` Over@1.5 at +270 (FanDuel), bet down to +251, 0.6u
- Man United v Brentford — **Kobbie Mainoo** `player_shots` Over@1.5 at +300 (BetRivers), bet down to +278, 0.6u
- Sunderland v Tottenham — **Noah Sadiki** `player_shots_on_target` Over@0.5 at +380 (BetRivers), bet down to +351, 0.6u
- Brighton v Newcastle — **Jacob Murphy** `player_to_receive_card` Yes at +650 (DraftKings), bet down to +584, 0.4u
- Chelsea v Crystal Palace — **Jordan Henderson** `player_goal_scorer_anytime` Yes at +700 (Bovada), bet down to +659, 0.4u

_Props carry the smallest stake the card uses: the standing measurement demonstrates no edge, and books reprice on the team sheet after this card is built._

### What changed

- **Added:** Arsenal v Man City corners_1x2 away
- **Added:** Brighton v Newcastle corners_1x2 away
- **Added:** Crystal Palace v Hull team_total_home_1_5 under
- **Added:** Fulham v Bournemouth corners_1x2 home
- **Added:** Leeds v Coventry corners_1x2 away
- **Added:** Man United v Brentford team_total_away_1_5 under
- **Added:** Nott'm Forest v Chelsea team_total_home_1_5 over
- **Added:** Sunderland v Tottenham 1x2 away


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at the card's base size (1u, or to win 1u on a minus price; the ladder from +200) for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### UEFA Nations League

National teams, on a pool that shares no information with the club ratings — a country has never played any club in them, so nothing bridges the two and this is a second model. It **cannot be backtested**: no free archive carries international prices, so it can only be judged forward, at roughly 80 matches a year. **Only the result markets are bet here.** Measured against the de-vigged market across 45 live fixtures, the model put the chance of over 2.5 goals at 0.418 where the market said 0.499 — eight points low, the same way on every fixture — so `total_2_5` and `btts` are priced by a standing gap rather than by the fixture, and are withheld. Three of the first four selections this section ever made were low-scoring bets off that gap. The baselines are now this competition's own rather than the pool's, which halved a separate bias: it was applying +0.656 goals of home advantage where the Nations League's own is +0.346. Two expected problems measured out **not** to apply — seeding keeps League A away from League D, so 0.3% of fixtures have a favourite above 90% and none above 95%, and a rating survives squad turnover (r = +0.82 across seven years). One remains and cannot be fixed from the feed: 5.2% of these matches are at neutral venues and the price feed does not say which, so those carry a home advantage one side does not have.

| Match | Market | Selection | Bet down to | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|--:|:--|--:|
| Norway v England | `draw_no_bet` | away | -156 | +3.7% | -155 | BetMGM | 1.55 |

- 156 fixture(s) dropped as already kicked off: Albania v Belarus, Albania v Finland, Albania v San Marino, Andorra v Gibraltar, Andorra v Malta, Armenia v Cyprus, and 150 more.
- `btts` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- `total_2_5` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- Ratings include no result after 2026-11-17; the results archive runs about a month behind, so the current international window is not in the fit.
- No corner model: the pool carries no corner counts.

_Fitted but not bet: EFL Cup (Carabao) (0 of 0 fixtures rateable), UEFA Champions League (0 of 0 fixtures rateable), UEFA Europa League (0 of 0 fixtures rateable), UEFA Europa Conference League (0 of 0 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._


### Due List · goals and assists

Context only: no units, nothing here is a selection, and no edge is shown.

**Anytime goalscorer, over 0.5.** Listed: 10+ Premier League goals last season and a run of league appearances without a goal at the bar his total sets (20+ goals -> 4, 15-19 goals -> 6, 10-14 goals -> 8 straight games).

**Being due has meant scoring less often, not more.** Seasons 2022/23 to 2025/26: listed players had a goal in 18.7% of 380 next appearances, against 28.8% for the same qualifiers when not due (n = 2,270; difference -10.2%, 95% -14.5% to -5.8%). No price-based measurement exists: historical player-prop prices were never bought.

| Player | Team | Opp | Kickoff (UTC) | Last season | Drought (bar) | 1 in N for him | Status | Price |
|:--|:--|:--|:--|--:|:--|--:|:--|:--|
| Harry Wilson | Leeds United | Coventry City | 2026-11-28 15:00 | 10 goals, 28% of apps | 16 (8) | 1 in 183 | — | not posted |
| Danny Welbeck | Chelsea | Nottingham Forest | 2026-11-27 20:00 | 13 goals, 27% of apps | 13 (8) | 1 in 60 | — | +245 (DraftKings) |
| Viktor Gyökeres | Arsenal | Manchester City | 2026-11-29 16:30 | 14 goals, 28% of apps | 11 (8) | 1 in 36 | — | +240 (DraftKings) |
| Morgan Gibbs-White | Nottingham Forest | Chelsea | 2026-11-27 20:00 | 15 goals, 35% of apps | 8 (6) | 1 in 32 | — | +295 (DraftKings) |

**1+ assist, over 0.5.** Listed: 7+ Premier League assists last season and a run of league appearances without an assist at the bar his total sets (12+ assists -> 8, 9-11 assists -> 10, 7-8 assists -> 13 straight games).

**Being due has meant assisting less often, not more.** Seasons 2022/23 to 2025/26: listed players had an assist in 10.3% of 448 next appearances, against 17.8% for the same qualifiers when not due (n = 2,484; difference -7.5%, 95% -10.7% to -4.3%). No price-based measurement exists: historical player-prop prices were never bought.

| Player | Team | Opp | Kickoff (UTC) | Last season | Drought (bar) | 1 in N for him | Status | Price |
|:--|:--|:--|:--|--:|:--|--:|:--|:--|
| Rayan Cherki | Manchester City | Arsenal | 2026-11-29 16:30 | 12 assists, 27% of apps | 9 (8) | 1 in 18 | — | +280 (FanDuel) |
| James Garner | Everton | Liverpool | 2026-11-29 12:00 | 7 assists, 18% of apps | 14 (13) | 1 in 17 | — | +600 (FanDuel) |

### How the recommendations have done

- Settled: **197** selections, 82 won, 8 returned the stake
- Staked: 199.50 units
- Profit: **-1.71 units** (-0.9% on turnover)
- Still pending: 19

- Stake returned (void): 8 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 1 staked selection(s) from that section are on this card. It is graded on a record of its own (`beyond_record.md`): 113 settled, 43 won, 8 returned the stake, -1.88 units. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

### Closing-line check by market

Consensus CLV on each market's picks, judged once it has 50 with a closing price. Cutting or raising a market is your call; this says where the evidence points.

- `corners_1x2`: 22 of 50 picks needed, not judged yet.
- `corners_total_9_5`: 19 of 50 picks needed, not judged yet.
- `corners_total_10_5`: 18 of 50 picks needed, not judged yet.
- `draw_no_bet`: 18 of 50 picks needed, not judged yet.
- `team_total_away_1_5`: 16 of 50 picks needed, not judged yet.
- `team_total_home_1_5`: 15 of 50 picks needed, not judged yet.
- `1x2`: 13 of 50 picks needed, not judged yet.
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

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/46013595591)
