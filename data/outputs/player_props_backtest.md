# Player Props Backtest

Model opinions against the prices that were actually for sale, walk-forward, flat stakes. Read-only: no picks, no card, no ledger, no policy, no bets.

- Priced outcomes with a model opinion: 19939
- Outcomes the model held no opinion on: 1321
- Edge threshold: 8%
- Calibration split: fitted before 2026-04-01, measured on and after it. Everything below — bets, ROI, and both tables — is the held-out window only.
- Fitted correction: sigmoid(-0.2383 + 0.9133 x logit(p)), from 7254 pre-split outcomes.

## Per market

| Market | Bets | Settled | Voids | Wins | Hit rate | Units | ROI |
|:-------|-----:|--------:|------:|-----:|---------:|------:|----:|
| `player_goal_scorer_anytime` | 3 | 3 | 0 | 0 | 0.0% | -3.0 | -100.0% |
| `player_shots_on_target` | 1 | 1 | 0 | 1 | 100.0% | 4.0 | 400.0% |

## Calibration

Every priced outcome that settled, bet or not — this is where the sample has power (7589 probability-outcome pairs).

### all

| Predicted | n | Mean predicted | Actual rate |
|:----------|--:|---------------:|------------:|
| 0%-10% | 5293 | 2.7% | 3.4% |
| 10%-20% | 1298 | 14.4% | 15.2% |
| 20%-30% | 530 | 24.3% | 24.5% |
| 30%-40% | 232 | 34.4% | 34.9% |
| 40%-50% | 145 | 44.3% | 51.0% |
| 50%-60% | 67 | 54.3% | 47.8% |
| 60%-70% | 20 | 63.7% | 80.0% |
| 70%-80% | 4 | 74.4% | 100.0% |

### player_goal_scorer_anytime

| Predicted | n | Mean predicted | Actual rate |
|:----------|--:|---------------:|------------:|
| 0%-10% | 1156 | 4.2% | 4.8% |
| 10%-20% | 338 | 14.4% | 15.1% |
| 20%-30% | 135 | 24.3% | 25.2% |
| 30%-40% | 30 | 33.0% | 26.7% |
| 40%-50% | 5 | 42.5% | 100.0% |

### player_shots_on_target

| Predicted | n | Mean predicted | Actual rate |
|:----------|--:|---------------:|------------:|
| 0%-10% | 4137 | 2.3% | 3.0% |
| 10%-20% | 960 | 14.4% | 15.2% |
| 20%-30% | 395 | 24.3% | 24.3% |
| 30%-40% | 202 | 34.7% | 36.1% |
| 40%-50% | 140 | 44.4% | 49.3% |
| 50%-60% | 67 | 54.3% | 47.8% |
| 60%-70% | 20 | 63.7% | 80.0% |
| 70%-80% | 4 | 74.4% | 100.0% |

## Calibration before the correction (same held-out window)

### all (raw)

| Predicted | n | Mean predicted | Actual rate |
|:----------|--:|---------------:|------------:|
| 0%-10% | 5211 | 2.5% | 3.3% |
| 10%-20% | 1202 | 14.4% | 13.3% |
| 20%-30% | 581 | 24.3% | 22.7% |
| 30%-40% | 270 | 34.5% | 31.9% |
| 40%-50% | 160 | 44.8% | 45.6% |
| 50%-60% | 96 | 54.1% | 49.0% |
| 60%-70% | 55 | 63.7% | 52.7% |
| 70%-80% | 13 | 74.2% | 92.3% |
| 80%-90% | 1 | 84.9% | 100.0% |

### player_goal_scorer_anytime (raw)

| Predicted | n | Mean predicted | Actual rate |
|:----------|--:|---------------:|------------:|
| 0%-10% | 1129 | 4.0% | 4.9% |
| 10%-20% | 323 | 14.5% | 12.1% |
| 20%-30% | 141 | 24.3% | 22.7% |
| 30%-40% | 59 | 33.3% | 33.9% |
| 40%-50% | 11 | 43.9% | 63.6% |
| 50%-60% | 1 | 51.6% | 100.0% |

### player_shots_on_target (raw)

| Predicted | n | Mean predicted | Actual rate |
|:----------|--:|---------------:|------------:|
| 0%-10% | 4082 | 2.1% | 2.9% |
| 10%-20% | 879 | 14.4% | 13.8% |
| 20%-30% | 440 | 24.3% | 22.7% |
| 30%-40% | 211 | 34.9% | 31.3% |
| 40%-50% | 149 | 44.9% | 44.3% |
| 50%-60% | 95 | 54.1% | 48.4% |
| 60%-70% | 55 | 63.7% | 52.7% |
| 70%-80% | 13 | 74.2% | 92.3% |
| 80%-90% | 1 | 84.9% | 100.0% |

## Unmatched players

- Abdukodir Khusanov
- Adam Aznou
- Airidas Golambeckis
- Andre Harriman-Annous
- Archie Whitehall
- Ben Hammond
- Benjamin Arthur
- Brendan Aaronson
- Charlie Tasker
- Chrisantus Uche
- Christopher Rigg
- Connor Roberts
- Daniel Ballard
- Diego Leon
- Edward Nketiah
- Felipe Rodrigues Da Silva
- Freddie Simmonds
- Harrison Jones
- Ibrahim Konate
- Iliya Gruev
- Jack Thompson
- Jake O'Brien
- Jeanricner Bellegarde
- Jimmy Sinclair
- Joe Gomez
- Joseph Willock
- Josh King
- Joshua Kofi Acheampong
- Jun'ai Byfield
- Landon Emenalo
- Leo Fuhr Hjelde
- Lesley Ugochukwu
- Luca Williams-Barnett
- Luke O'Nien
- Malachi Hardy
- Matthew O'Riley
- Matty Cash
- Mickey van de Ven
- Mike Ndayishimiye
- Milan Aleksic
- Nicolas Gonzalez Iglesias
- Niko O'Reilly
- No Scorer
- Norberto Bercique Gomes Betuncal
- Rayan Cherki
- Reggie Walsh
- Rhys Chadwick-Chaplin
- Rio Kyerematen
- Ryan Kavuma-McQueen
- Sam Amissah
- Seth Ky Ridgeon
- Seung-soo Park
- Tijani Reijnders
- Toluwalase Emmanuel Arokodare
- Trent Toure Kone-Doherty
- Trey Nyoni
- Tynan Thompson
- Vitaliy Mykolenko
- Yehor Yarmoliuk

## Caveats

- Prices are one-sided (Over/Yes only); implied probabilities are un-devigged and overstate truth, so edges here are understated.
- Shots on target settle on the Understat definition (Goal or SavedShot), close to but not identical to Opta counts.
- This sample cannot separate a real edge from zero (~1,500 bets needed); it is calibration-grade evidence only.
