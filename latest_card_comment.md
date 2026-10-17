## Saturday 17 October, 07:18 UTC — scheduled run

Selections changed: 4 added, 5 dropped, 2 moved section.

Provider quota: 75667 (about 75 days at the observed burn)

Markets: **total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5** (excluded: 1x2)

### Best bets

| Match | Market | Selection | Tier | Edge | Price | Book | Units |
|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|
| Everton v Chelsea | `corners_1x2` | away | C | +6.0% | +105 | DraftKings | 0.1 |
| Leeds v Man United | `corners_1x2` | home | C | +5.7% | +120 | FanDuel | 0.1 |
| Bournemouth v Sunderland | `corners_total_9_5` | over | C | +3.8% | -114 | FanDuel | 0.1 |
| Fulham v Hull | `corners_1x2` | away | C | +5.4% | +400 | DraftKings | 0.1 |
| Tottenham v Coventry | `corners_1x2` | away | C | +5.3% | +450 | DraftKings | 0.1 |
| Brighton v Crystal Palace | `draw_no_bet` | away | C | +5.3% | +390 | FanDuel | 0.1 |
| Newcastle v Aston Villa | `corners_total_10_5` | over | C | +4.3% | +130 | FanDuel | 0.1 |
| Brighton v Crystal Palace | `double_chance` | draw_or_away | C | +4.0% | +150 | BetRivers | 0.1 |

### Leans

_None._

### What changed

- **Added:** Everton v Chelsea corners_1x2 away
- **Added:** Man City v Ipswich draw_no_bet home
- **Added:** Newcastle v Aston Villa btts no
- **Added:** Tottenham v Coventry corners_1x2 draw
- **Dropped:** Bournemouth v Sunderland corners_total_10_5 over
- **Dropped:** Man City v Ipswich btts yes
- **Dropped:** Man City v Ipswich corners_total_9_5 over
- **Dropped:** Nott'm Forest v Arsenal corners_total_10_5 over
- **Dropped:** Nott'm Forest v Arsenal corners_total_9_5 over
- **Moved section:** Brighton v Crystal Palace double_chance draw_or_away
- **Moved section:** Fulham v Hull draw_no_bet away


## Beyond the Premier League

Nothing below has been shown to beat a price. Some of it has been shown not to, and some of it cannot be tested at all. Each section says which. They are staked at 0.1 units for that reason. See `data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.

### EFL Cup (Carabao)

Priced on the unified English ratings. Measured out of sample, a club's rating does **not** survive a division change — carrying it across is worse than calling the club average for its new division. What transfers is the division, which the market also knows.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Fulham v Crystal Palace | `btts` | no | +4.8% | +130 | BetMGM | 0.1 |
| Fulham v Crystal Palace | `total_2_5` | under | +2.2% | +115 | BetMGM | 0.1 |
| Sunderland v Brentford | `total_2_5` | under | +0.3% | -105 | Bovada | 0.1 |

- 10 fixture(s) dropped as already kicked off: Coventry v Aston Villa, Everton v Wolves, Fleetwood Town v Sheffield United, Ipswich v Arsenal, Liverpool v Tottenham, Man City v Norwich, and 4 more.
- 1 fixture(s) left out because a club has no rating in the pool: Bradford City v Peterborough United.

### UEFA Champions League

Priced on the European ratings, where 868 European ties bridge eleven leagues onto one scale — 7.45% better than a league-average prior on held-out ties. That scale **overrates clubs who dominate weak leagues**, and those are the clubs it will most often call value.

| Match | Market | Selection | Edge | Price | Book | Units |
|:--|:--|:--|--:|--:|:--|--:|
| Man City v AEK | `total_2_5` | under | +11.4% | +300 | FanDuel | 0.1 |
| Como v Man United | `corners_1x2` | home | +7.1% | -120 | BetRivers | 0.1 |
| Real Madrid v RB Leipzig | `corners_total_9_5` | under | +6.9% | +133 | BetRivers | 0.1 |
| Como v Man United | `draw_no_bet` | home | +6.0% | -140 | DraftKings | 0.1 |

- 18 fixture(s) dropped as already kicked off: AS Roma v Real Madrid, Arsenal v Lille, Aston Villa v Fenerbahce, Atlético Madrid v Man United, Bodø/Glimt v Borussia Dortmund, Feyenoord v Como, and 12 more.
- 7 fixture(s) left out because a club has no rating in the pool: Aston Villa v Viking FK, Fenerbahce v Slavia Praha, Inter v Shakhtar Donetsk, Napoli v Bodø/Glimt, Roma v ŠK Slovan Bratislava, Sabah FK v Dortmund, Sp Lisbon v LASK.
- 19 further selection(s) qualified and are not shown: this section prints at most 4 per competition, the highest edges first.

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
- 10 fixture(s) left out because a club has no rating in the pool: AS Monaco v SC Freiburg, Ajax v Atalanta BC, FC Kairat v Panathinaikos FC, FC Midtjylland v Sint Truiden, FC Nordsjaelland v PFC CSKA Sofia, FK Jablonec v Brighton, Inter Club d'Escaldes v Universitatea Craiova, Pafos FC v Riga FC, Red Star Belgrade v FC Copenhagen, SC Braga v Gent.
- None of 4 priced selections cleared the rules.

_Fitted but not bet: UEFA Nations League (0 of 0 fixtures rateable). Their results still bridge the countries in the rating pool — which is most of their value — and they return to the card on their own the run they can price something._

### How the recommendations have done

- Settled: **105** selections, 46 won, 6 returned the stake
- Staked: 13.35 units
- Profit: **-0.16 units** (-1.2% on turnover)
- Still pending: 10

- Stake returned (void): 6 — counted in the settled total above at zero profit, because a push is a bet

Each selection is scored at the first price a card offered it, and only rows the card staked are counted — a lean carries no stake and is not a recommendation.

**Beyond the Premier League is not in these numbers.** 10 staked selection(s) from that section are recorded and not yet scored — nothing settles them. The rule above is stated by stake, so without this line the only way to notice would be to total the card by hand.

This is the only out-of-sample evidence this project has. It will take a long time to mean anything: separating a real 5% edge from zero needs roughly 1,500 settled bets.

---

Recommendations only. No bet was placed and no settlement was applied.

You get one card a day while the schedule runs, plus a message whenever a run goes wrong. So **a day with no message at all means a run did not happen.**

[Full run summary](https://github.com/cooperross399/epl-betting-lab/actions/runs/39012826049)
