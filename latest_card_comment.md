## Sunday 18 October, 13:07 UTC — scheduled run

Selections changed: 21 dropped.

Provider quota: 68728 (about 68 days at the observed burn)

Markets: **total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5** (excluded: 1x2)

### Best bets

| Match | Market | Selection | Tier | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|
| Tottenham v Coventry | `corners_1x2` | away | C | +7.1% | +400 | DraftKings | 0.1 |

### Leans

_None._

### What changed

- **Dropped:** Bournemouth v Sunderland btts yes
- **Dropped:** Bournemouth v Sunderland corners_1x2 draw
- **Dropped:** Bournemouth v Sunderland corners_total_10_5 over
- **Dropped:** Bournemouth v Sunderland corners_total_9_5 over
- **Dropped:** Bournemouth v Sunderland double_chance home_or_away
- **Dropped:** Bournemouth v Sunderland total_2_5 over
- **Dropped:** Brighton v Crystal Palace btts yes
- **Dropped:** Brighton v Crystal Palace corners_1x2 draw
- **Dropped:** Brighton v Crystal Palace corners_total_10_5 under
- **Dropped:** Brighton v Crystal Palace corners_total_9_5 under
- **Dropped:** Brighton v Crystal Palace double_chance draw_or_away
- **Dropped:** Brighton v Crystal Palace draw_no_bet away
- **Dropped:** Leeds v Man United btts yes
- **Dropped:** Leeds v Man United corners_1x2 draw
- **Dropped:** Leeds v Man United corners_1x2 home
- **Dropped:** Leeds v Man United corners_total_10_5 over
- **Dropped:** Leeds v Man United corners_total_9_5 over
- **Dropped:** Leeds v Man United double_chance draw_or_away
- **Dropped:** Leeds v Man United draw_no_bet away
- **Dropped:** Nott'm Forest v Arsenal corners_total_10_5 over
- **Dropped:** Nott'm Forest v Arsenal draw_no_bet away


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at 0.1 units for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### EFL Cup (Carabao)

Priced on the unified English ratings. Measured out of sample, a club's rating does **not** survive a division change — carrying it across is worse than calling the club average for its new division. What transfers is the division, which the market also knows.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Fulham v Crystal Palace | `btts` | no | +4.8% | +130 | BetMGM | 0.1 |
| Fulham v Crystal Palace | `total_2_5` | under | +2.2% | +115 | BetMGM | 0.1 |

- 10 fixture(s) dropped as already kicked off: Coventry v Aston Villa, Everton v Wolves, Fleetwood Town v Sheffield United, Ipswich v Arsenal, Liverpool v Tottenham, Man City v Norwich, and 4 more.
- 1 fixture(s) left out because a club has no rating in the pool: Bradford City v Peterborough United.
- 1 selection(s) cleared their market rule and were refused because the edge against the posted price is not positive: Sunderland v Brentford total_2_5 under. A refused row always sorts below every positive one, so where 4 or more selections qualify this costs the card nothing; the cap line below is the one that says what was actually withheld.

### UEFA Champions League

Priced on the European ratings, where 868 European ties bridge eleven leagues onto one scale — 7.45% better than a league-average prior on held-out ties. That scale **overrates clubs who dominate weak leagues**, and those are the clubs it will most often call value.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Man City v AEK | `total_2_5` | under | +10.5% | +265 | BetRivers | 0.1 |
| Como v Man United | `corners_1x2` | home | +7.1% | -120 | BetRivers | 0.1 |
| Paris SG v Barcelona | `corners_1x2` | home | +7.1% | +143 | BetRivers | 0.1 |
| Real Madrid v RB Leipzig | `corners_total_10_5` | under | +7.1% | -125 | BetRivers | 0.1 |

- 18 fixture(s) dropped as already kicked off: AS Roma v Real Madrid, Arsenal v Lille, Aston Villa v Fenerbahce, Atlético Madrid v Man United, Bodø/Glimt v Borussia Dortmund, Feyenoord v Como, and 12 more.
- 7 fixture(s) left out because a club has no rating in the pool: Aston Villa v Viking FK, Fenerbahce v Slavia Praha, Inter v Shakhtar Donetsk, Napoli v Bodø/Glimt, Roma v ŠK Slovan Bratislava, Sabah FK v Dortmund, Sp Lisbon v LASK.
- 20 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

### UEFA Europa League

Same European ratings as the Champions League, and **thinner in both directions**: more clubs come from countries with no domestic feed, so more fixtures are declined, and the ones that are priced rest on a scale calibrated mostly by Champions League ties.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Juventus v Rennes | `draw_no_bet` | away | +6.0% | +310 | FanDuel | 0.1 |
| OFI Crete v Leverkusen | `btts` | yes | +4.5% | -128 | FanDuel | 0.1 |
| OFI Crete v Leverkusen | `total_2_5` | under | +1.4% | +200 | FanDuel | 0.1 |

- 36 fixture(s) dropped as already kicked off: AC Milan v Benfica, AZ Alkmaar v Hapoel Be'er Sheva, Anderlecht v Lyon, Bayer Leverkusen v NK Celje, Benfica v Celtic, Besiktas JK v Marseille, and 30 more.
- 16 fixture(s) left out because a club has no rating in the pool: Besiktas JK v Crystal Palace, Bournemouth v AC Milan, Celtic v Celta Vigo, Dinamo Zagreb v NEC Nijmegen, FC Ararat-Armenia v AZ Alkmaar, Ferencváros TC v Torreense, Jagiellonia Białystok v Anderlecht, Lech Poznań v Sunderland, Lillestrom v Sociedad, NK Celje v Salzburg, Olympiakos Piraeus v Sparta Prague, Omonoia FC v Benfica, SK Sturm Graz v Marseille, St. Gilloise v Hapoel Be'er Sheva, TSG Hoffenheim v Lyon, Viktoria Plzeň v PFC Levski Sofia.

### UEFA Europa Conference League

The thinnest of the three. Only 24 Conference League ties survive club resolution across five seasons, against 701 for the Champions League — both resolved counts, and together with the Europa League's 143 they are the 868-tie bridge. So this competition contributes almost nothing to the scale it is priced on, and most of its fixtures involve a club the pool cannot rate at all.

_No selection this run._

- 18 fixture(s) dropped as already kicked off: Atalanta BC v Pafos FC, Brighton v FK Kauno Žalgiris, FC Copenhagen v SC Braga, FC Lugano v Red Star Belgrade, FC Twente Enschede v FC Thun, Gent v AGF Aarhus, and 12 more.
- 17 fixture(s) left out because a club has no rating in the pool: AGF Aarhus v KF Egnatia, AS Monaco v SC Freiburg, Ajax v Atalanta BC, FC Iberia 1999 v Mjällby AIF, FC Kairat v Panathinaikos FC, FC Midtjylland v Sint Truiden, FC Nordsjaelland v PFC CSKA Sofia, FC Thun v Hajduk Split, FK Borac Banja Luka v KuPS Kuopio, FK Jablonec v Brighton, FK Kauno Žalgiris v SK Brann, Getafe v FC Lugano, Inter Club d'Escaldes v Universitatea Craiova, Lincoln Red Imps FC v FC Twente Enschede, Pafos FC v Riga FC, Red Star Belgrade v FC Copenhagen, SC Braga v Gent.
- 1 selection(s) cleared their market rule and were refused because the edge against the posted price is not positive: Trabzonspor v Hearts total_2_5 under. A refused row always sorts below every positive one, so where 4 or more selections qualify this costs the card nothing; the cap line below is the one that says what was actually withheld.
- None of 4 priced selections cleared the rules with a positive edge against the price offered.

_Fitted but not bet: UEFA Nations League (0 of 0 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._


### Due List · anytime goalscorers

Anytime goalscorer, over 0.5. Listed: 10+ Premier League goals last season and a run of league appearances without a goal at the bar his total sets (20+ goals -> 4, 15-19 goals -> 6, 10-14 goals -> 8 straight games). Context only: no units, nothing here is a selection, and no edge is shown.

**Being due has meant scoring less often, not more.** Seasons 2022/23 to 2025/26: listed players scored in 18.0% of 388 next appearances, against 28.6% for the same qualifiers when not due (n = 2,286; difference -10.6%, 95% -14.8% to -6.3%). No price-based measurement exists: historical goalscorer prices were never bought.

Nobody playing in this round is due.

### How the recommendations have done

- Settled: **105** selections, 46 won, 6 returned the stake
- Staked: 13.35 units
- Profit: **-0.16 units** (-1.2% on turnover)
- Still pending: 1
- Played, waiting on results data: **12** — these are settled matches the results feed has not caught up with, so the record above is behind rather than still accumulating.

- Stake returned (void): 6 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 9 staked selection(s) from that section are recorded and not yet scored — nothing settles them. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/39129850651)
