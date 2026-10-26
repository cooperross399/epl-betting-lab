## Monday 26 October, 10:30 UTC — scheduled run

Selections changed: 1 added, 5 dropped, 2 moved section.

Provider quota: **43268** — about 12 day(s) at the observed burn. **Top this up or the schedule stops.**

Markets: **1x2, total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5, team_total_home_0_5, team_total_home_1_5, team_total_home_2_5, team_total_away_0_5, team_total_away_1_5, team_total_away_2_5** (excluded: none)

### Best bets

| Match | Market | Selection | Tier | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|
| Coventry v Sunderland | `draw_no_bet` | away | C | +7.0% | -138 | Bovada | 0.1 |
| Liverpool v Arsenal | `draw_no_bet` | away | C | +6.3% | -142 | FanDuel | 0.1 |
| Coventry v Sunderland | `team_total_away_1_5` | under | C | +5.5% | -155 | Bovada | 0.1 |
| Newcastle v Everton | `draw_no_bet` | home | C | +5.5% | -140 | FanDuel | 0.1 |
| Hull v Ipswich | `team_total_away_1_5` | under | C | +5.3% | -157 | Bovada | 0.1 |
| Newcastle v Everton | `1x2` | home | C | +6.6% | +126 | BetUS | 0.1 |
| Coventry v Sunderland | `corners_1x2` | home | C | +5.3% | -118 | BetRivers | 0.1 |
| Chelsea v Man United | `double_chance` | draw_or_away | C | +5.4% | -104 | BetRivers | 0.1 |

### Leans

_None._

### Player props

- Chelsea v Man United — **Jordan Henderson** `player_shots_on_target` Over@0.5 at +310 (BetRivers), 0.1u
- Hull v Ipswich — **Regan Slater** `player_shots_on_target` Over@0.5 at +380 (BetRivers), 0.1u
- Chelsea v Man United — **Jordan Henderson** `player_goal_scorer_anytime` Yes at +860 (MyBookie.ag), 0.1u
- Tottenham v Crystal Palace — **Adam Wharton** `player_shots_on_target` Over@0.5 at +450 (BetRivers), 0.1u
- Bournemouth v Leeds — **Ethan Ampadu** `player_shots_on_target` Over@0.5 at +480 (BetRivers), 0.1u

_Props carry the smallest stake the card uses: the standing measurement demonstrates no edge, and books reprice on the team sheet after this card is built._

### What changed

- **Added:** Bournemouth v Leeds corners_1x2 away
- **Dropped:** Bournemouth v Leeds corners_total_10_5 under
- **Dropped:** Hull v Ipswich corners_1x2 home
- **Dropped:** Hull v Ipswich corners_total_10_5 over
- **Dropped:** Hull v Ipswich corners_total_9_5 over
- **Dropped:** Tottenham v Crystal Palace team_total_away_0_5 over
- **Moved section:** Chelsea v Man United corners_total_9_5 over
- **Moved section:** Coventry v Sunderland corners_1x2 home


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at 0.1 units for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### EFL Cup (Carabao)

Priced on the unified English ratings. Measured out of sample, a club's rating does **not** survive a division change — carrying it across is worse than calling the club average for its new division. What transfers is the division, which the market also knows.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Fulham v Crystal Palace | `total_2_5` | under | +3.5% | +125 | BetRivers | 0.1 |
| Sunderland v Brentford | `total_2_5` | under | +1.2% | -102 | Bovada | 0.1 |

- 10 fixture(s) dropped as already kicked off: Coventry v Aston Villa, Everton v Wolves, Fleetwood Town v Sheffield United, Ipswich v Arsenal, Liverpool v Tottenham, Man City v Norwich, and 4 more.
- 1 fixture(s) left out because a club has no rating in the pool: Bradford City v Peterborough United.

### UEFA Champions League

Priced on the European ratings, where 868 European ties bridge eleven leagues onto one scale — 7.45% better than a league-average prior on held-out ties. That scale **overrates clubs who dominate weak leagues**, and those are the clubs it will most often call value.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| AEK v Real Madrid | `total_2_5` | under | +8.7% | +245 | FanDuel | 0.1 |
| Ath Madrid v Bayern Munich | `corners_total_10_5` | under | +6.8% | -152 | BetRivers | 0.1 |
| AEK v Real Madrid | `corners_total_10_5` | under | +6.7% | -159 | BetRivers | 0.1 |
| Porto v Napoli | `corners_total_9_5` | under | +6.2% | -113 | BetRivers | 0.1 |

- 36 fixture(s) dropped as already kicked off: AS Roma v Real Madrid, AS Roma v ŠK Slovan Bratislava, Arsenal v Lille, Aston Villa v Fenerbahce, Aston Villa v Viking FK, Atlético Madrid v Man United, and 30 more.
- 5 fixture(s) left out because a club has no rating in the pool: Bodø/Glimt v Lille, LASK v ŠK Slovan Bratislava, Shakhtar Donetsk v Sp Lisbon, Slavia Praha v Arsenal, Viking FK v Sabah FK.
- 17 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### UEFA Europa League

Same European ratings as the Champions League, and **thinner in both directions**: more clubs come from countries with no domestic feed, so more fixtures are declined, and the ones that are priced rest on a scale calibrated mostly by Champions League ties.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Sociedad v Lyon | `double_chance` | draw_or_away | +7.2% | -130 | FanDuel | 0.1 |
| AZ Alkmaar v Juventus | `double_chance` | home_or_draw | +6.6% | -140 | DraftKings | 0.1 |

- 54 fixture(s) dropped as already kicked off: AC Milan v Benfica, AZ Alkmaar v Hapoel Be'er Sheva, Anderlecht v Lyon, Bayer Leverkusen v NK Celje, Benfica v Celtic, Besiktas JK v Crystal Palace, and 48 more.
- 15 fixture(s) left out because a club has no rating in the pool: AC Milan v Ferencváros TC, Anderlecht v Salzburg, Benfica v Lech Poznań, Celta Vigo v St. Gilloise, Celtic v Besiktas JK, Crystal Palace v TSG Hoffenheim, Hapoel Be'er Sheva v OFI Crete, Lillestrom v Viktoria Plzeň, NEC Nijmegen v Omonoia FC, PFC Levski Sofia v Jagiellonia Białystok, Rennes v Olympiakos Piraeus, SK Sturm Graz v NK Celje, Sparta Prague v Bournemouth, Sunderland v Dinamo Zagreb, Torreense v FC Ararat-Armenia.

_Fitted but not bet: UEFA Nations League (0 of 0 fixtures rateable), UEFA Europa Conference League (0 of 0 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._


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
- Still pending: 9

- Stake returned (void): 7 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 8 staked selection(s) from that section are recorded and not yet scored — nothing settles them. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/40307149467)
