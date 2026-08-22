# Player Props Backtest

Model opinions against the prices that were actually for sale, walk-forward, flat stakes. Read-only: no picks, no card, no ledger, no policy, no bets.

- Priced outcomes with a model opinion: 19939
- Outcomes the model held no opinion on: 1321
- Edge threshold: 8%

## Per market

| Market | Bets | Settled | Voids | Wins | Hit rate | Units | ROI |
|:-------|-----:|--------:|------:|-----:|---------:|------:|----:|
| `player_goal_scorer_anytime` | 16 | 15 | 1 | 6 | 40.0% | 13.6 | 90.7% |
| `player_shots_on_target` | 26 | 22 | 4 | 8 | 36.4% | 2.48 | 11.3% |

## Calibration

Every priced outcome that settled, bet or not — this is where the sample has power (14843 probability-outcome pairs).

### all

| Predicted | n | Mean predicted | Actual rate |
|:----------|--:|---------------:|------------:|
| 0%-10% | 10025 | 2.6% | 3.0% |
| 10%-20% | 2474 | 14.5% | 13.9% |
| 20%-30% | 1124 | 24.4% | 21.5% |
| 30%-40% | 545 | 34.4% | 31.0% |
| 40%-50% | 342 | 44.7% | 43.9% |
| 50%-60% | 193 | 54.1% | 50.8% |
| 60%-70% | 114 | 64.1% | 50.9% |
| 70%-80% | 25 | 74.0% | 80.0% |
| 80%-90% | 1 | 84.9% | 100.0% |

### player_goal_scorer_anytime

| Predicted | n | Mean predicted | Actual rate |
|:----------|--:|---------------:|------------:|
| 0%-10% | 2179 | 4.0% | 4.5% |
| 10%-20% | 668 | 14.5% | 12.1% |
| 20%-30% | 291 | 24.3% | 22.3% |
| 30%-40% | 117 | 33.5% | 26.5% |
| 40%-50% | 26 | 43.7% | 46.2% |
| 50%-60% | 1 | 51.6% | 100.0% |

### player_shots_on_target

| Predicted | n | Mean predicted | Actual rate |
|:----------|--:|---------------:|------------:|
| 0%-10% | 7846 | 2.2% | 2.6% |
| 10%-20% | 1806 | 14.5% | 14.5% |
| 20%-30% | 833 | 24.4% | 21.2% |
| 30%-40% | 428 | 34.7% | 32.2% |
| 40%-50% | 316 | 44.8% | 43.7% |
| 50%-60% | 192 | 54.1% | 50.5% |
| 60%-70% | 114 | 64.1% | 50.9% |
| 70%-80% | 25 | 74.0% | 80.0% |
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
