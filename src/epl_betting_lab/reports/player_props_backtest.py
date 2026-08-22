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
from epl_betting_lab.models.player_props import (
    PlayerPropsModel,
    PropCalibration,
)

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


#: Letters NFKD cannot reduce because they are not base-plus-combining forms.
#: Without these, "Nørgaard" never equals "Norgaard" however the accents are
#: stripped.
_LETTER_FALLBACKS = str.maketrans(
    {
        "ø": "o",
        "Ø": "O",
        "æ": "ae",
        "Æ": "AE",
        "ð": "d",
        "Ð": "D",
        "þ": "th",
        "Þ": "Th",
        "ł": "l",
        "Ł": "L",
        "ß": "ss",
        "đ": "d",
        "Đ": "D",
    }
)


def _player_key(name: str) -> str:
    """Accent- and punctuation-insensitive identity for a player name."""
    text = str(name).translate(_LETTER_FALLBACKS)
    text = unicodedata.normalize("NFKD", text)
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
    calibration_split: str | None = None,
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

    # Books spell players their own way — extra surnames ("Carlos Baleba Noom
    # Quomah"), or the surname alone ("Casemiro"). When the exact key misses,
    # a name whose tokens contain or are contained by exactly one squad
    # player's tokens is that player; any ambiguity stays unmatched.
    squad_tokens: dict[str, list[tuple[str, frozenset[str]]]] = {}
    for (team_key_value, player_key_value), _rows in logs.groupby(
        ["team_key", "player_key"]
    ):
        squad_tokens.setdefault(str(team_key_value), []).append(
            (str(player_key_value), frozenset(str(player_key_value).split()))
        )

    def _resolve_player_key(
        book_key: str, home_key: str, away_key: str
    ) -> str | None:
        tokens = frozenset(book_key.split())
        candidates: set[str] = set()
        for team in (home_key, away_key):
            for player_key_value, player_tokens in squad_tokens.get(team, []):
                if player_key_value == book_key:
                    return player_key_value
                if player_tokens and (
                    player_tokens <= tokens or tokens <= player_tokens
                ):
                    candidates.add(player_key_value)
        if len(candidates) == 1:
            return next(iter(candidates))
        return None

    unmatched_teams: set[str] = set()
    unmatched_players: set[str] = set()
    records: list[dict[str, object]] = []
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
        resolved = _resolve_player_key(
            _player_key(row["player"]), home_key, away_key
        )
        if resolved is None:
            unmatched_players.add(str(row["player"]))
            continue
        player_key = resolved
        date = row["date"]

        # The player's appearance in this fixture, if any: identity is the
        # date plus either team plus the resolved name.
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
        settled = not appearance.empty
        line = point if point is not None else 0.5
        records.append(
            {
                "date": date,
                "market": market,
                "player": str(row["player"]),
                "selection": str(row["selection"]),
                "american": american,
                "raw_probability": probability,
                "settled": settled,
                "won": (
                    float(appearance[stat].iloc[0]) > line if settled else None
                ),
            }
        )

    # The correction is fitted strictly before the split and applied strictly
    # after it; without a split, probabilities pass through untouched. Fitting
    # and measuring on the same window would launder overconfidence into ROI.
    correction: PropCalibration | None = None
    if calibration_split:
        correction = PropCalibration.fit(
            [
                (float(r["raw_probability"]), bool(r["won"]))
                for r in records
                if r["settled"] and str(r["date"]) < calibration_split
            ]
        )
        evaluation = [r for r in records if str(r["date"]) >= calibration_split]
    else:
        evaluation = records
    for record in records:
        raw = float(record["raw_probability"])
        record["probability"] = correction.apply(raw) if correction else raw

    bets: list[PropBet] = []
    for record in evaluation:
        american = float(record["american"])
        implied = _implied_probability(american)
        probability = float(record["probability"])
        edge = probability - implied
        if edge < edge_threshold:
            continue
        if not record["settled"]:
            outcome, profit = "void", 0.0
        elif record["won"]:
            outcome, profit = "won", _profit(american)
        else:
            outcome, profit = "lost", -1.0
        bets.append(
            PropBet(
                date=str(record["date"]),
                market=str(record["market"]),
                player=str(record["player"]),
                selection=str(record["selection"]),
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

    def _tables(probability_field: str) -> dict[str, list[dict[str, object]]]:
        samples_by_market: list[tuple[str, float, bool]] = [
            (
                str(r["market"]),
                float(r[probability_field]),
                bool(r["won"]),
            )
            for r in evaluation
            if r["settled"]
        ]
        tables: dict[str, list[dict[str, object]]] = {}
        markets_present = sorted({m for m, _, _ in samples_by_market})
        for market_name in ["all", *markets_present]:
            samples = [
                (p, won)
                for m, p, won in samples_by_market
                if market_name == "all" or m == market_name
            ]
            buckets = []
            for lower in (i / 10 for i in range(10)):
                upper = lower + 0.1
                inside = [
                    (p, won)
                    for p, won in samples
                    if lower <= p < upper or (upper >= 1.0 and p >= 0.9999)
                ]
                if not inside:
                    continue
                buckets.append(
                    {
                        "bucket": f"{lower:.0%}-{upper:.0%}",
                        "n": len(inside),
                        "mean_predicted": round(
                            sum(p for p, _ in inside) / len(inside), 4
                        ),
                        "actual_rate": round(
                            sum(1 for _, won in inside if won) / len(inside), 4
                        ),
                    }
                )
            tables[market_name] = buckets
        return tables

    settled_evaluation = sum(1 for r in evaluation if r["settled"])
    calibration = _tables("probability")
    calibration_raw = _tables("raw_probability") if correction else None

    return {
        "priced_outcomes": priced,
        "no_model_opinion": no_opinion,
        "settled_calibration_samples": settled_evaluation,
        "edge_threshold": edge_threshold,
        "calibration_split": calibration_split,
        "calibration_correction": (
            {
                "intercept": round(correction.intercept, 4),
                "slope": round(correction.slope, 4),
                "fitted_on": correction.fitted_on,
            }
            if correction
            else None
        ),
        "bets": [b.__dict__ for b in bets],
        "per_market": per_market,
        "calibration": calibration,
        "calibration_raw": calibration_raw,
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
    ]
    correction = summary.get("calibration_correction")
    if correction:
        lines += [
            f"- Calibration split: fitted before {summary['calibration_split']}, "
            "measured on and after it. Everything below — bets, ROI, and both "
            "tables — is the held-out window only.",
            f"- Fitted correction: sigmoid({correction['intercept']} + "
            f"{correction['slope']} x logit(p)), from "
            f"{correction['fitted_on']} pre-split outcomes.",
        ]
    lines += [
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
    lines += [
        "",
        "## Calibration",
        "",
        "Every priced outcome that settled, bet or not — this is where the "
        f"sample has power ({summary['settled_calibration_samples']} "
        "probability-outcome pairs).",
    ]
    def _render_tables(tables: Mapping[str, object], suffix: str = "") -> None:
        for market_name, buckets in tables.items():
            lines.append("")
            lines.append(f"### {market_name}{suffix}")
            lines.append("")
            lines.append("| Predicted | n | Mean predicted | Actual rate |")
            lines.append("|:----------|--:|---------------:|------------:|")
            for bucket in buckets:
                lines.append(
                    f"| {bucket['bucket']} | {bucket['n']} | "
                    f"{bucket['mean_predicted']:.1%} | "
                    f"{bucket['actual_rate']:.1%} |"
                )

    _render_tables(summary["calibration"])
    if summary.get("calibration_raw"):
        lines += [
            "",
            "## Calibration before the correction (same held-out window)",
        ]
        _render_tables(summary["calibration_raw"], suffix=" (raw)")
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
