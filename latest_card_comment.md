## Saturday 31 October, 10:36 UTC — scheduled run

Selections changed: 7 added, 7 dropped, 1 moved section.

Provider quota: **26065** — about 7 day(s) at the observed burn. **Top this up or the schedule stops.**

Markets: **1x2, total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5, team_total_home_0_5, team_total_home_1_5, team_total_home_2_5, team_total_away_0_5, team_total_away_1_5, team_total_away_2_5** (excluded: none)

### Best bets

| Match | Market | Selection | Tier | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|
| Chelsea v Man United | `double_chance` | draw_or_away | C | +7.5% | -129 | BetRivers | 0.1 |
| Liverpool v Arsenal | `team_total_away_1_5` | under | C | +7.0% | -143 | Bovada | 0.1 |
| Newcastle v Everton | `draw_no_bet` | home | C | +5.7% | -138 | FanDuel | 0.1 |
| Bournemouth v Leeds | `team_total_home_1_5` | over | C | +5.9% | +114 | FanDuel | 0.1 |
| Liverpool v Arsenal | `draw_no_bet` | away | C | +4.8% | -128 | FanDuel | 0.1 |
| Tottenham v Crystal Palace | `team_total_home_1_5` | under | C | +6.0% | +130 | Bovada | 0.1 |
| Newcastle v Everton | `1x2` | home | C | +5.7% | +136 | BetOnline.ag | 0.1 |
| Tottenham v Crystal Palace | `team_total_away_1_5` | over | C | +6.1% | +240 | FanDuel | 0.1 |

### Leans

_None._

### Player props

- Chelsea v Man United — **Jordan Henderson** `player_goal_scorer_anytime` Yes at +1300 (Fanatics), 0.1u
- Chelsea v Man United — **Jordan Henderson** `player_shots_on_target` Over@0.5 at +225 (BetRivers), 0.1u
- Hull v Ipswich — **Regan Slater** `player_shots_on_target` Over@0.5 at +380 (BetRivers), 0.1u
- Tottenham v Crystal Palace — **Quinten Timber** `player_shots` Over@0.5 at -143 (BetRivers), 0.1u
- Hull v Ipswich — **Regan Slater** `player_shots` Over@1.5 at +250 (FanDuel), 0.1u
- Tottenham v Crystal Palace — **Adam Wharton** `player_shots_on_target` Over@0.5 at +450 (BetRivers), 0.1u
- Chelsea v Man United — **Jordan Henderson** `player_shots` Over@1.5 at +145 (BetRivers), 0.1u
- Bournemouth v Leeds — **Ethan Ampadu** `player_shots_on_target` Over@0.5 at +500 (BetRivers), 0.1u
- Tottenham v Crystal Palace — **Adam Wharton** `player_shots` Over@0.5 at -130 (BetRivers), 0.1u

_Props carry the smallest stake the card uses: the standing measurement demonstrates no edge, and books reprice on the team sheet after this card is built._

### What changed

- **Added:** Aston Villa v Fulham draw_no_bet away
- **Added:** Bournemouth v Leeds team_total_away_0_5 under
- **Added:** Bournemouth v Leeds team_total_home_1_5 over
- **Added:** Coventry v Sunderland corners_total_10_5 over
- **Added:** Tottenham v Crystal Palace 1x2 draw
- **Added:** Tottenham v Crystal Palace team_total_away_1_5 over
- **Added:** Tottenham v Crystal Palace team_total_home_2_5 under
- **Dropped:** Aston Villa v Fulham double_chance draw_or_away
- **Dropped:** Aston Villa v Fulham team_total_home_0_5 under
- **Dropped:** Liverpool v Arsenal corners_1x2 home
- **Dropped:** Man City v Brighton double_chance draw_or_away
- **Dropped:** Man City v Brighton draw_no_bet away
- **Dropped:** Man City v Brighton team_total_home_0_5 under
- **Dropped:** Man City v Brighton team_total_home_2_5 under
- **Moved section:** Man City v Brighton team_total_home_1_5 under


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at 0.1 units for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### UEFA Nations League

National teams, on a pool that shares no information with the club ratings — a country has never played any club in them, so nothing bridges the two and this is a second model. It **cannot be backtested**: no free archive carries international prices, so it can only be judged forward, at roughly 80 matches a year. **Only the result markets are bet here.** Measured against the de-vigged market across 45 live fixtures, the model put the chance of over 2.5 goals at 0.418 where the market said 0.499 — eight points low, the same way on every fixture — so `total_2_5` and `btts` are priced by a standing gap rather than by the fixture, and are withheld. Three of the first four selections this section ever made were low-scoring bets off that gap. The baselines are now this competition's own rather than the pool's, which halved a separate bias: it was applying +0.656 goals of home advantage where the Nations League's own is +0.346. Two expected problems measured out **not** to apply — seeding keeps League A away from League D, so 0.3% of fixtures have a favourite above 90% and none above 95%, and a rating survives squad turnover (r = +0.82 across seven years). One remains and cannot be fixed from the feed: 5.2% of these matches are at neutral venues and the price feed does not say which, so those carry a home advantage one side does not have.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Italy v France | `draw_no_bet` | home | +5.2% | +175 | BetMGM | 0.1 |

- 103 fixture(s) dropped as already kicked off: Albania v Belarus, Albania v San Marino, Andorra v Malta, Armenia v Latvia, Armenia v Montenegro, Austria v Israel, and 97 more.
- `btts` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- `total_2_5` is not bet here: the model sits about 8 points below the market on the goals level for every fixture, so a selection in that market would be the gap rather than the fixture.
- Ratings include no result after 2026-10-06; the results archive runs about a month behind, so the current international window is not in the fit.
- No corner model: the pool carries no corner counts.

### EFL Cup (Carabao)

Priced on the unified English ratings. Measured out of sample, a club's rating does **not** survive a division change — carrying it across is worse than calling the club average for its new division. What transfers is the division, which the market also knows.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Fleetwood Town v Everton | `total_2_5` | under | +5.6% | +114 | BetRivers | 0.1 |

- 18 fixture(s) dropped as already kicked off: Bournemouth v Aston Villa, Bradford City v Peterborough United, Coventry v Aston Villa, Everton v Newcastle, Everton v Wolves, Fleetwood Town v Arsenal, and 12 more.
- 3 fixture(s) dropped because their kickoff could not be confirmed from the feed: Crystal Palace v Sunderland, Liverpool v Bournemouth, Man City v Bradford City.

### UEFA Champions League

Priced on the European ratings, where 868 European ties bridge eleven leagues onto one scale — 7.45% better than a league-average prior on held-out ties. That scale **overrates clubs who dominate weak leagues**, and those are the clubs it will most often call value.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| AEK v Real Madrid | `total_2_5` | under | +6.7% | +245 | FanDuel | 0.1 |
| Villarreal v Paris SG | `draw_no_bet` | home | +6.6% | +270 | FanDuel | 0.1 |
| Lens v Como | `btts` | no | +6.1% | +166 | FanDuel | 0.1 |
| RB Leipzig v Man City | `double_chance` | home_or_draw | +5.8% | +150 | FanDuel | 0.1 |

- 36 fixture(s) dropped as already kicked off: AS Roma v Real Madrid, AS Roma v ŠK Slovan Bratislava, Arsenal v Lille, Aston Villa v Fenerbahce, Aston Villa v Viking FK, Atlético Madrid v Man United, and 30 more.
- 5 fixture(s) left out because a club has no rating in the pool: Bodø/Glimt v Lille, LASK v ŠK Slovan Bratislava, Shakhtar Donetsk v Sp Lisbon, Slavia Praha v Arsenal, Viking FK v Sabah FK.
- 13 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### UEFA Europa League

Same European ratings as the Champions League, and **thinner in both directions**: more clubs come from countries with no domestic feed, so more fixtures are declined, and the ones that are priced rest on a scale calibrated mostly by Champions League ties.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| AZ Alkmaar v Juventus | `draw_no_bet` | home | +6.0% | +164 | FanDuel | 0.1 |
| AZ Alkmaar v Juventus | `double_chance` | home_or_draw | +5.5% | -130 | DraftKings | 0.1 |
| Sociedad v Lyon | `draw_no_bet` | away | +5.4% | +164 | FanDuel | 0.1 |
| Leverkusen v Marseille | `btts` | yes | +4.9% | -148 | FanDuel | 0.1 |

- 54 fixture(s) dropped as already kicked off: AC Milan v Benfica, AZ Alkmaar v Hapoel Be'er Sheva, Anderlecht v Lyon, Bayer Leverkusen v NK Celje, Benfica v Celtic, Besiktas JK v Crystal Palace, and 48 more.
- 1 fixture(s) dropped because their kickoff could not be confirmed from the feed: Rennes v Olympiakos Piraeus.
- 14 fixture(s) left out because a club has no rating in the pool: AC Milan v Ferencváros TC, Anderlecht v Salzburg, Benfica v Lech Poznań, Celta Vigo v St. Gilloise, Celtic v Besiktas JK, Crystal Palace v TSG Hoffenheim, Hapoel Be'er Sheva v OFI Crete, Lillestrom v Viktoria Plzeň, NEC Nijmegen v Omonoia FC, PFC Levski Sofia v Jagiellonia Białystok, SK Sturm Graz v NK Celje, Sparta Prague v Bournemouth, Sunderland v Dinamo Zagreb, Torreense v FC Ararat-Armenia.
- 1 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### UEFA Europa Conference League

The thinnest of the three. Only 24 Conference League ties survive club resolution across five seasons, against 701 for the Champions League — both resolved counts, and together with the Europa League's 143 they are the 868-tie bridge. So this competition contributes almost nothing to the scale it is priced on, and most of its fixtures involve a club the pool cannot rate at all.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Getafe v Brighton | `total_2_5` | under | +2.4% | -120 | Bovada | 0.1 |

- 36 fixture(s) dropped as already kicked off: AGF Aarhus v KF Egnatia, AS Monaco v SC Freiburg, Ajax v Atalanta BC, Atalanta BC v Pafos FC, Brighton v FK Kauno Žalgiris, FC Copenhagen v SC Braga, and 30 more.
- 17 fixture(s) left out because a club has no rating in the pool: AGF Aarhus v SC Braga, AS Monaco v FC Nordsjaelland, Atalanta BC v FC Kairat, FC Copenhagen v FC Iberia 1999, FC Lugano v FK Kauno Žalgiris, FC Midtjylland v Ajax, FC Thun v Hearts, FC Twente Enschede v Pafos FC, KuPS Kuopio v Gent, Lincoln Red Imps FC v Hajduk Split, Mjällby AIF v FK Borac Banja Luka, Panathinaikos FC v PFC CSKA Sofia, Red Star Belgrade v Inter Club d'Escaldes, Riga FC v FK Jablonec, Sint Truiden v SK Brann, Trabzonspor v SC Freiburg, Universitatea Craiova v KF Egnatia.


### Due List · goals and assists

Context only: no units, nothing here is a selection, and no edge is shown.

**Anytime goalscorer, over 0.5.** Listed: 10+ Premier League goals last season and a run of league appearances without a goal at the bar his total sets (20+ goals -> 4, 15-19 goals -> 6, 10-14 goals -> 8 straight games).

**Being due has meant scoring less often, not more.** Seasons 2022/23 to 2025/26: listed players had a goal in 18.7% of 380 next appearances, against 28.8% for the same qualifiers when not due (n = 2,270; difference -10.2%, 95% -14.5% to -5.8%). No price-based measurement exists: historical player-prop prices were never bought.

| Player | Team | Opp | Kickoff (UTC) | Last season | Drought (bar) | 1 in N for him | Status | Price |
|:--|:--|:--|:--|--:|:--|--:|:--|:--|
| Harry Wilson | Leeds United | AFC Bournemouth | 2026-10-31 15:00 | 10 goals, 28% of apps | 13 (8) | 1 in 69 | — | not posted |
| Danny Welbeck | Chelsea | Manchester United | 2026-10-31 12:30 | 13 goals, 27% of apps | 10 (8) | 1 in 23 | — | not posted |
| Viktor Gyökeres | Arsenal | Liverpool | 2026-11-01 16:30 | 14 goals, 28% of apps | 8 (8) | 1 in 14 | — | not posted |

**1+ assist, over 0.5.** Listed: 7+ Premier League assists last season and a run of league appearances without an assist at the bar his total sets (12+ assists -> 8, 9-11 assists -> 10, 7-8 assists -> 13 straight games).

**Being due has meant assisting less often, not more.** Seasons 2022/23 to 2025/26: listed players had an assist in 10.3% of 448 next appearances, against 17.8% for the same qualifiers when not due (n = 2,484; difference -7.5%, 95% -10.7% to -4.3%). No price-based measurement exists: historical player-prop prices were never bought.

Nobody playing in this round is due.

### How the recommendations have done

- Settled: **142** selections, 54 won, 7 returned the stake
- Staked: 17.05 units
- Profit: **-2.07 units** (-12.1% on turnover)
- Still pending: 23

- Stake returned (void): 7 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 11 staked selection(s) from that section are on this card. It is graded on a record of its own (`beyond_record.md`): 48 settled, 19 won, 1 returned the stake, -0.66 units. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

### Closing-line check by market

Consensus CLV on each market's picks, judged once it has 50 with a closing price. Cutting or raising a market is your call; this says where the evidence points.

- `corners_total_9_5`: 19 of 50 picks needed, not judged yet.
- `corners_total_10_5`: 18 of 50 picks needed, not judged yet.
- `corners_1x2`: 17 of 50 picks needed, not judged yet.
- `draw_no_bet`: 13 of 50 picks needed, not judged yet.
- `double_chance`: 9 of 50 picks needed, not judged yet.
- `1x2`: 4 of 50 picks needed, not judged yet.
- `team_total_away_1_5`: 4 of 50 picks needed, not judged yet.
- `team_total_home_1_5`: 4 of 50 picks needed, not judged yet.
- `btts`: 3 of 50 picks needed, not judged yet.
- `team_total_away_0_5`: 0 of 50 picks needed, not judged yet.
- `total_2_5`: 0 of 50 picks needed, not judged yet.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/41192895114)
