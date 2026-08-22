"""Measure player props against the prices that were actually for sale.

The house rule is that no market is enabled on modelling alone: it must be
measured against real historical prices first. For props the pieces are the
harvested per-event prices (`historical_market_odds.csv`, `player` column
required), the Understat match logs (`player_match_logs.csv`) for results,
and `PlayerPropsModel` for the opinion — fitted walk-forward, only on
appearances dated before the fixture being priced, so the model never reads
a result it is being scored on.

What a bet is here: for each priced outcome the model can hold an opinion
on, compare model probability to the price's implied probability; when the
edge clears the threshold, stake one flat unit. Settlement follows book
practice: a player who never entered voids the bet (stake returned), an
Over wins when the actual count exceeds the line, anytime scorer wins on
one goal or more.

Three caveats are printed into the report because the numbers cannot show
them:

**The prices are one-sided.** Books quote Over/Yes only, so there is no
market-implied No side to lean on and the juice on the quoted side cannot
be split against a counterpart. Implied probability here is the quoted
side's own, un-devigged — which overstates the true probability and
therefore *understates* model edges. The measurement is conservative in
that one direction.

**Shots on target settle on the Understat definition** (Goal or SavedShot),
close to but not identical to the Opta counts books actually settle by.

**Sample size rules everything.** A hundred-odd fixtures cannot separate a
real edge from zero — the repository's own arithmetic puts that at about
1,500 bets. This report is calibration-grade evidence: it can rule the
model out, not in.

Read-only: no picks, no card, no ledger, no policy, no bets.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR, PROCESSED_DIR, PROJECT_ROOT
from epl_betting_lab.models.player_props import PlayerPropsModel

BACKTEST_JSON_FILENAME = "player_props_backtest.json"
BACKTEST_MARKDOWN_FILENAME = "player_props_backtest.md"
BACKTEST_CSV_FILENAME = "player_props_backtest.csv"

#: Provider prop market -> the log column it settles on.
SETTLEMENT_COLUMNS = {
    "player_shots_on_target": "shots_on_target",
    "player_shots": "shots",
    "player_assists": "assists",
    "player_goal_scorer_anytime": "goals",
}

#: Minimum modelled edge to count a bet, per the flat-stake measurement.
#: Higher than the card's match-level bar on purpose: the model prices the
#: morning, books reprice on the team sheet.
DEFAULT_EDGE_THRESHOLD = 0.08

#: Provider and Understat spell teams differently. Both spellings map here to
#: one key; a fixture whose teams cannot be mapped is reported, not guessed.
TEAM_ALIASES = {
    "arsenal": "arsenal",
    "aston villa": "aston villa",
    "bournemouth": "bournemouth",
    "afc bournemouth": "bournemouth",
    "brentford": "brentford",
    "brighton": "brighton",
    "brighton and hove albion": "brighton",
    "burnley": "burnley",
    "chelsea": "chelsea",
    "coventry": "coventry",
    "coventry city": "coventry",
    "crystal palace": "crystal palace",
    "everton": "everton",
    "fulham": "fulham",
    "hull": "hull",
    "hull city": "hull",
    "ipswich": "ipswich",
    "ipswich town": "ipswich",
    "leeds": "leeds",
    "leeds united": "leeds",
    "leicester": "leicester",
    "leicester city": "leicester",
    "liverpool": "liverpool",
    "luton": "luton",
    "luton town": "luton",
    "manchester city": "manchester city",
    "man city": "manchester city",
    "manchester united": "manchester united",
    "man united": "manchester united",
    "newcastle": "newcastle",
    "newcastle united": "newcastle",
    "nottingham forest": "nottingham forest",
    "nott'm forest": "nottingham forest",
    "sheffield united": "sheffield united",
    "southampton": "southampton",
    "sunderland": "sunderland",
    "tottenham": "tottenham",
    "tottenham hotspur": "tottenham",
    "west ham": "west ham",
    "west ham united": "west ham",
    "wolverhampton wanderers": "wolves",
    "wolves": "wolves",
}


def _team_key(name: str) -> str:
    return TEAM_ALIASES.get(str(name).strip().casefold(), "")


def _player_key(name: str) -> str:
    """Accent- and punctuation-insensitive identity for a player name."""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.casefold().replace("-", " ").replace(".", " ").replace("'", "")
    return " ".join(text.split())


def _implied_probability(american: float) -> float:
    if american >= 100:
        return 100.0 / (american + 100.0)
    return -american / (-american + 100.0)


def _profit(american: float) -> float:
    """Flat one-unit profit on a win."""
    if american >= 100:
        return american / 100.0
    return 100.0 / -american


def _parse_selection(selection: str) -> tuple[str, float | None]:
    text = str(selection).strip()
    if "@" in text:
        name, _, point = text.partition("@")
        try:
            return name.strip(), float(point)
        except ValueError:
            return name.strip(), None
    return text, None


@dataclass
class PropBet:
    date: str
    market: str
    player: str
    selection: str
    american: float
    model_probability: float
    implied_probability: float
    edge: float
    outcome: str  # "won" | "lost" | "void"
    profit: float


def build_player_props_backtest(
    *,
    odds_path: Path | None = None,
    logs_path: Path | None = None,
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD,
    repository_root: Path | None = None,
) -> dict[str, object]:
    root = (repository_root or PROJECT_ROOT).resolve()
    selected_odds = odds_path or Path(PROCESSED_DIR) / "historical_market_odds.csv"
    selected_logs = logs_path or Path(PROCESSED_DIR) / "player_match_logs.csv"
    for label, path in (("odds", selected_odds), ("player logs", selected_logs)):
        if not Path(path).is_file():
            raise FileNotFoundError(
                f"The {label} file is missing: {path}. Nothing is measured "
                "from an absent dataset."
            )

    odds = pd.read_csv(selected_odds, dtype=str)
    if "player" not in odds.columns:
        raise KeyError(
            "The odds file has no `player` column; prop rows without a player "
            "collapsed the ladder and cannot be measured."
        )
    odds = odds[odds["market"].isin(SETTLEMENT_COLUMNS)].copy()
    odds = odds[odds["player"].fillna("").str.strip() != ""]
    odds["american"] = pd.to_numeric(odds["american"], errors="coerce")
    odds = odds.dropna(subset=["american"])
    odds["date"] = odds["commence_time"].str[:10]

    logs = pd.read_csv(selected_logs, dtype=str)
    for stat in set(SETTLEMENT_COLUMNS.values()) | {"minutes"}:
        logs[stat] = pd.to_numeric(logs[stat], errors="coerce").fillna(0)
    logs["team_key"] = logs["team"].map(_team_key)
    logs["player_key"] = logs["player"].map(_player_key)

    unmatched_teams: set[str] = set()
    unmatched_players: set[str] = set()
    bets: list[PropBet] = []
    priced = 0
    no_opinion = 0

    model_cache: dict[str, PlayerPropsModel | None] = {}

    def _model_before(date: str) -> PlayerPropsModel | None:
        if date not in model_cache:
            training = logs[logs["date"] < date]
            if len(training) < 500:
                model_cache[date] = None
            else:
                model_cache[date] = PlayerPropsModel().fit(training)
        return model_cache[date]

    for _, row in odds.sort_values(["date", "market", "player"]).iterrows():
        market = row["market"]
        stat = SETTLEMENT_COLUMNS[market]
        home_key = _team_key(row["home_team"])
        away_key = _team_key(row["away_team"])
        if not home_key or not away_key:
            unmatched_teams.add(f"{row['home_team']} v {row['away_team']}")
            continue
        player_key = _player_key(row["player"])
        date = row["date"]

        # The player's appearance in this fixture, if any: identity is the
        # date plus either team plus the normalised name.
        appearance = logs[
            (logs["date"] == date)
            & (logs["team_key"].isin({home_key, away_key}))
            & (logs["player_key"] == player_key)
        ]
        # Which side the player is on decides opponent and venue for the
        # model. When the player never appeared, the roster does not say;
        # the bet voids below and the model side is moot, but an opinion is
        # still needed first, so the squad list decides.
        squad = logs[
            (logs["player_key"] == player_key)
            & (logs["team_key"].isin({home_key, away_key}))
        ]
        if squad.empty:
            unmatched_players.add(str(row["player"]))
            continue
        team_key = squad["team_key"].iloc[-1]
        venue = "home" if team_key == home_key else "away"
        opponent_key = away_key if venue == "home" else home_key

        model = _model_before(date)
        if model is None:
            continue
        priced += 1

        # The model keys opponents by Understat team title; recover it from
        # the logs for this key.
        opponent_rows = logs[logs["team_key"] == opponent_key]
        opponent_title = (
            str(opponent_rows["team"].iloc[-1]) if not opponent_rows.empty else ""
        )
        model_player = (
            str(squad["player"].iloc[-1]) if not squad.empty else str(row["player"])
        )

        name, point = _parse_selection(row["selection"])
        if name.casefold() == "over" and point is not None:
            probability = model.over_probability(
                model_player, stat, point, opponent=opponent_title, venue=venue
            )
        elif market == "player_goal_scorer_anytime":
            probability = model.anytime_scorer_probability(
                model_player, opponent=opponent_title, venue=venue
            )
        else:
            probability = None
        if probability is None:
            no_opinion += 1
            continue

        american = float(row["american"])
        implied = _implied_probability(american)
        edge = probability - implied
        if edge < edge_threshold:
            continue

        if appearance.empty:
            outcome, profit = "void", 0.0
        else:
            actual = float(appearance[stat].iloc[0])
            threshold = point if point is not None else 0.5
            won = actual > threshold
            outcome = "won" if won else "lost"
            profit = _profit(american) if won else -1.0
        bets.append(
            PropBet(
                date=date,
                market=market,
                player=str(row["player"]),
                selection=str(row["selection"]),
                american=american,
                model_probability=round(probability, 4),
                implied_probability=round(implied, 4),
                edge=round(edge, 4),
                outcome=outcome,
                profit=round(profit, 4),
            )
        )

    per_market: dict[str, dict[str, object]] = {}
    for market in sorted({b.market for b in bets}):
        market_bets = [b for b in bets if b.market == market]
        settled = [b for b in market_bets if b.outcome != "void"]
        wins = sum(1 for b in settled if b.outcome == "won")
        profit = sum(b.profit for b in settled)
        per_market[market] = {
            "bets": len(market_bets),
            "settled": len(settled),
            "voids": len(market_bets) - len(settled),
            "wins": wins,
            "hit_rate": round(wins / len(settled), 4) if settled else None,
            "flat_profit_units": round(profit, 2),
            "roi": round(profit / len(settled), 4) if settled else None,
        }

    return {
        "priced_outcomes": priced,
        "no_model_opinion": no_opinion,
        "edge_threshold": edge_threshold,
        "bets": [b.__dict__ for b in bets],
        "per_market": per_market,
        "unmatched_teams": sorted(unmatched_teams),
        "unmatched_players": sorted(unmatched_players),
        "caveats": [
            "Prices are one-sided (Over/Yes only); implied probabilities are "
            "un-devigged and overstate truth, so edges here are understated.",
            "Shots on target settle on the Understat definition (Goal or "
            "SavedShot), close to but not identical to Opta counts.",
            "This sample cannot separate a real edge from zero (~1,500 bets "
            "needed); it is calibration-grade evidence only.",
        ],
    }


def save_player_props_backtest(
    output_dir: Path | None = None, **kwargs: object
) -> dict[str, object]:
    outputs = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    outputs.mkdir(parents=True, exist_ok=True)
    summary = build_player_props_backtest(**kwargs)  # type: ignore[arg-type]

    json_path = outputs / BACKTEST_JSON_FILENAME
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    frame = pd.DataFrame(summary["bets"])
    csv_path = outputs / BACKTEST_CSV_FILENAME
    frame.to_csv(csv_path, index=False)

    lines = [
        "# Player Props Backtest",
        "",
        "Model opinions against the prices that were actually for sale, "
        "walk-forward, flat stakes. Read-only: no picks, no card, no ledger, "
        "no policy, no bets.",
        "",
        f"- Priced outcomes with a model opinion: {summary['priced_outcomes']}",
        f"- Outcomes the model held no opinion on: {summary['no_model_opinion']}",
        f"- Edge threshold: {summary['edge_threshold']:.0%}",
        "",
        "## Per market",
        "",
        "| Market | Bets | Settled | Voids | Wins | Hit rate | Units | ROI |",
        "|:-------|-----:|--------:|------:|-----:|---------:|------:|----:|",
    ]
    for market, stats in summary["per_market"].items():
        hit = stats["hit_rate"]
        roi = stats["roi"]
        lines.append(
            f"| `{market}` | {stats['bets']} | {stats['settled']} | "
            f"{stats['voids']} | {stats['wins']} | "
            f"{'' if hit is None else format(hit, '.1%')} | "
            f"{stats['flat_profit_units']} | "
            f"{'' if roi is None else format(roi, '.1%')} |"
        )
    if summary["unmatched_teams"]:
        lines += ["", "## Unmatched fixtures", ""]
        lines += [f"- {item}" for item in summary["unmatched_teams"]]
    if summary["unmatched_players"]:
        lines += ["", "## Unmatched players", ""]
        lines += [f"- {item}" for item in summary["unmatched_players"]]
    lines += ["", "## Caveats", ""]
    lines += [f"- {item}" for item in summary["caveats"]]
    lines.append("")
    markdown_path = outputs / BACKTEST_MARKDOWN_FILENAME
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "summary": summary,
        "json": str(json_path),
        "markdown": str(markdown_path),
        "csv": str(csv_path),
    }
