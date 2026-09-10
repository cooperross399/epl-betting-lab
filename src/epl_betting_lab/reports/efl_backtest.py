"""Measure the model on the EFL, against prices the project already owns.

Football-Data publishes its own bookmaker prices in the same files as the
results — opening and closing, 1X2, over/under 2.5 and the Asian handicap. So
the question "does this model beat the market in the Championship" can be
answered without spending a single provider credit, which matters when the
provider pool is shared with sibling labs and measured in days.

**Two honesty constraints shape this module, and both are load-bearing.**

*It is a goals model, not the blend the card bets.* Understat publishes xG for
six top-tier leagues and no English division below the Premier League. The card
fits a 70/30 xG blend; `PoissonGoalsModel` falls back to goals row by row when
xG is absent, and `load_matches_with_xg` creates the columns filled with NaN, so
an EFL run would have produced a goals model reporting itself as a blend. This
module therefore asks for goals explicitly, and every report it writes says so.
What is measured here is not what the EPL card bets, and no number from this
file should be compared with an EPL number as though it were.

*Only three markets can be priced here, and the card bets seven.* Football-Data
quotes 1X2, over/under 2.5 and the Asian handicap. It does not quote both teams
to score, double chance, or anything on corners — the corner *counts* are in the
file, the corner *prices* are not. Those four markets are unmeasured rather than
measured-and-fine, and the report says which is which, because a market missing
from a results table reads exactly like a market that had nothing to say.

The primary price is the closing average across books. Closing is the hard test:
it is the market's last and best word, and a model that only beats opening
prices has found staleness rather than an edge. Opening is reported beside it
precisely so the two can be compared — a rule that wins at the open and loses at
the close is a rule that is merely fast.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, RatingConfig

#: One EFL season is 24 teams x 46 matches / 2. The EPL backtest uses 380 for
#: the same reason: a model should not bet a division until it has seen a full
#: season of it, and promoted or relegated sides arrive with no history in the
#: pool at all.
MIN_TRAINING_MATCHES = 552

#: A returned stake. A level-ball Asian handicap voids on a draw, so the bet
#: happened and belongs in the denominator at zero profit — it is not a loss and
#: it is not an absence.
PUSH = "push"

#: The markets the live card bets. Naming them here lets the report state which
#: were measured and which could not be, rather than quietly listing three.
CARD_MARKETS = (
    "total_2_5",
    "btts",
    "double_chance",
    "draw_no_bet",
    "corners_1x2",
    "corners_total_9_5",
    "corners_total_10_5",
)

#: Why each unmeasured card market is unmeasured. An empty row in a results
#: table is ambiguous; a reason is not.
UNPRICED_REASON = {
    "btts": "Football-Data quotes no both-teams-to-score price.",
    "double_chance": (
        "Football-Data quotes no double-chance price. It could be derived from "
        "the 1X2 prices, but a derived price is not one anybody could have "
        "taken — books charge more for the combination — and betting it would "
        "manufacture an edge out of the arithmetic."
    ),
    "corners_1x2": "Football-Data carries corner counts (HC/AC) but no corner prices.",
    "corners_total_9_5": "Football-Data carries corner counts (HC/AC) but no corner prices.",
    "corners_total_10_5": "Football-Data carries corner counts (HC/AC) but no corner prices.",
}


@dataclass(frozen=True)
class PriceSet:
    """One set of columns to read prices from, and what it means."""

    key: str
    label: str
    #: market -> selection -> column holding that selection's decimal price
    columns: dict[str, dict[str, str]]
    #: The column holding the Asian handicap line, so a level ball can be found.
    handicap_column: str


CLOSING_AVERAGE = PriceSet(
    key="closing_average",
    label="closing average across books",
    columns={
        "1x2": {"home": "AvgCH", "draw": "AvgCD", "away": "AvgCA"},
        "total_2_5": {"over": "AvgC>2.5", "under": "AvgC<2.5"},
        "draw_no_bet": {"home": "AvgCAHH", "away": "AvgCAHA"},
    },
    handicap_column="AHCh",
)

OPENING_AVERAGE = PriceSet(
    key="opening_average",
    label="opening average across books",
    columns={
        "1x2": {"home": "AvgH", "draw": "AvgD", "away": "AvgA"},
        "total_2_5": {"over": "Avg>2.5", "under": "Avg<2.5"},
        "draw_no_bet": {"home": "AvgAHH", "away": "AvgAHA"},
    },
    handicap_column="AHh",
)

PRICE_SETS = (CLOSING_AVERAGE, OPENING_AVERAGE)

#: Which model probability answers which selection. `match_probabilities`
#: returns all of these from one score matrix, so the 1X2 and draw-no-bet
#: numbers are the same numbers combined and cannot disagree.
PROBABILITY_KEYS = {
    "1x2": {"home": "home_win", "draw": "draw", "away": "away_win"},
    "total_2_5": {"over": "over_2_5", "under": "under_2_5"},
    "draw_no_bet": {"home": "draw_no_bet_home", "away": "draw_no_bet_away"},
}

MEASURABLE_MARKETS = tuple(PROBABILITY_KEYS)

#: Edge thresholds reported side by side. One number at one threshold invites
#: the reader to assume it was the only one tried; the sweep shows the shape.
EDGE_THRESHOLDS = (0.0, 0.02, 0.03, 0.05, 0.08)

#: The threshold the headline uses.
HEADLINE_THRESHOLD = 0.03


@dataclass
class EflBacktestResult:
    division: str
    bets: pd.DataFrame
    notes: list[str] = field(default_factory=list)
    trained_from: pd.Timestamp | None = None
    matches_seen: int = 0
    matches_bet: int = 0


def _goals_only_config() -> RatingConfig:
    """The card's rating shape, with the one thing the EFL cannot have removed.

    `RatingConfig.btts()` and friends ask for `goal_source="blend"`. Asking for
    it here would not fail — it would silently produce a goals model, because
    every EFL row has NaN xG. So goals are requested explicitly, and the report
    says the model is not the card's.
    """
    return RatingConfig(
        opponent_adjusted=True,
        half_life_days=365,
        goal_source="goals",
    )


def _decimal(value: object) -> float:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return float("nan")
    # A decimal price below 1.01 is not a price; it is a blank, a zero, or a
    # parsing accident. Betting one would pay out less than the stake.
    return price if price >= 1.01 else float("nan")


def profit_from_decimal(price: float, outcome: bool | str) -> float:
    """Units won or lost on a one-unit stake at a decimal price."""
    if outcome is PUSH:
        return 0.0
    return (price - 1.0) if outcome else -1.0


def settle(market: str, selection: str, home_goals: float, away_goals: float) -> bool | str | None:
    """Did the selection win, lose, or come back?"""
    if pd.isna(home_goals) or pd.isna(away_goals):
        return None
    home, away = int(home_goals), int(away_goals)
    if market == "1x2":
        winner = "home" if home > away else ("away" if away > home else "draw")
        return selection == winner
    if market == "total_2_5":
        over = (home + away) > 2.5
        return over if selection == "over" else not over
    if market == "draw_no_bet":
        if home == away:
            return PUSH
        return (home > away) if selection == "home" else (away > home)
    raise ValueError(f"No settlement rule for market {market!r}")


def _priceable(row: pd.Series, market: str, prices: PriceSet) -> bool:
    """Is this market actually quoted on this row, in this price set?

    Draw-no-bet is the one that needs asking. Football-Data quotes an Asian
    handicap on every match, but only a level ball — handicap 0 — is
    draw-no-bet. A -0.5 line is a different bet with a different settlement,
    and reading its price as draw-no-bet would grade a bet nobody placed.
    """
    if market != "draw_no_bet":
        return True
    line = pd.to_numeric(pd.Series([row.get(prices.handicap_column)]), errors="coerce").iloc[0]
    return bool(pd.notna(line) and float(line) == 0.0)


def run_division(
    matches: pd.DataFrame,
    division: str,
    *,
    min_training: int = MIN_TRAINING_MATCHES,
    price_sets: tuple[PriceSet, ...] = PRICE_SETS,
) -> EflBacktestResult:
    """Walk forward through one division, betting only on what was already known.

    The model is refitted once per match date on every match that had been
    played strictly before it. Refitting per date rather than per match is not
    a shortcut: matches on the same day cannot inform each other anyway.
    """
    notes: list[str] = []
    frame = matches.dropna(subset=["home_goals", "away_goals"]).copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    if frame.empty:
        return EflBacktestResult(division=division, bets=pd.DataFrame(), notes=["No matches."])

    available = {p.key: p for p in price_sets}
    for price_set in price_sets:
        wanted = [c for cols in price_set.columns.values() for c in cols.values()]
        absent = [c for c in wanted if c not in frame.columns]
        if absent:
            notes.append(
                f"Price set `{price_set.key}` is unavailable: the dataset has no "
                f"{', '.join(absent)}. It was skipped rather than filled in."
            )
            available.pop(price_set.key, None)

    rows: list[dict[str, object]] = []
    dates = list(dict.fromkeys(frame["date"].tolist()))
    matches_bet = 0
    trained_from: pd.Timestamp | None = None

    for day in dates:
        history = frame[frame["date"] < day]
        if len(history) < min_training:
            continue
        if trained_from is None:
            trained_from = day
        model = PoissonGoalsModel().fit(history, config=_goals_only_config())
        today = frame[frame["date"] == day]

        for _, match in today.iterrows():
            home, away = match["home_team"], match["away_team"]
            # A side with no history in this pool has no rating. The model
            # would fall back to a league-average team, which is a guess
            # wearing a number - promoted and relegated sides arrive every
            # summer, so this is routine rather than exotic.
            if not _has_history(history, home) or not _has_history(history, away):
                continue
            try:
                probabilities = model.match_probabilities(home, away)
            except Exception:
                continue
            _check_probability_keys(probabilities)
            matches_bet += 1
            for market, selections in PROBABILITY_KEYS.items():
                for selection, probability_key in selections.items():
                    probability = float(probabilities.get(probability_key, float("nan")))
                    if not np.isfinite(probability) or probability <= 0:
                        continue
                    outcome = settle(market, selection, match["home_goals"], match["away_goals"])
                    if outcome is None:
                        continue
                    for price_set in available.values():
                        if not _priceable(match, market, price_set):
                            continue
                        column = price_set.columns[market][selection]
                        price = _decimal(match.get(column))
                        if not np.isfinite(price):
                            continue
                        rows.append(
                            {
                                "division": division,
                                "date": match["date"],
                                "home_team": home,
                                "away_team": away,
                                "market": market,
                                "selection": selection,
                                "price_set": price_set.key,
                                "probability": probability,
                                "price": price,
                                "edge": probability * price - 1.0,
                                "outcome": outcome,
                                "profit": profit_from_decimal(price, outcome),
                            }
                        )

    bets = pd.DataFrame(rows)
    if bets.empty:
        notes.append(
            f"No match in {division} had {min_training} earlier matches to train on, "
            "so nothing was priced."
        )
    return EflBacktestResult(
        division=division,
        bets=bets,
        notes=notes,
        trained_from=trained_from,
        matches_seen=len(frame),
        matches_bet=matches_bet,
    )


def _check_probability_keys(probabilities: dict) -> None:
    """Fail loudly when a market's probability key is not what the model returns.

    `probabilities.get(key)` returns None for a name that does not exist, the
    selection is skipped, and the market disappears from the report while every
    other market still looks fine. The first run of this module asked for
    `over_25` and `dnb_home` — the model returns `over_2_5` and
    `draw_no_bet_home` — so two of the three markets silently produced nothing
    and the output was a clean-looking 1X2 table. Nothing raised.
    """
    wrong = {
        f"{market}.{selection}={key}"
        for market, selections in PROBABILITY_KEYS.items()
        for selection, key in selections.items()
        if key not in probabilities
    }
    if wrong:
        raise KeyError(
            "match_probabilities does not return "
            f"{', '.join(sorted(wrong))}. It returns "
            f"{', '.join(sorted(k for k in probabilities if isinstance(probabilities[k], float)))}. "
            "A missing key drops its market from the report in silence."
        )


def _has_history(history: pd.DataFrame, team: str) -> bool:
    return bool(((history["home_team"] == team) | (history["away_team"] == team)).any())


def bootstrap_interval(
    bets: pd.DataFrame, *, draws: int = 2000, seed: int = 12345
) -> tuple[float, float, float]:
    """95% interval for ROI, resampling whole matches.

    Selections on one match share a result, so resampling rows would treat
    correlated bets as independent and report an interval that is too narrow.
    Identical in method to the EPL backtest's, deliberately: two measurements
    that disagree about their own uncertainty cannot be compared at all.
    """
    if bets.empty:
        return (float("nan"), float("nan"), float("nan"))
    groups = [
        group["profit"].to_numpy()
        for _, group in bets.groupby(["date", "home_team", "away_team"], sort=True)
    ]
    rng = np.random.default_rng(seed)
    count = len(groups)
    rois = np.empty(draws)
    for draw in range(draws):
        picked = rng.integers(0, count, count)
        rois[draw] = np.concatenate([groups[index] for index in picked]).mean() * 100.0
    return (
        float(np.percentile(rois, 2.5)),
        float(np.percentile(rois, 97.5)),
        float((rois > 0).mean()),
    )


def summarize(bets: pd.DataFrame, *, threshold: float = HEADLINE_THRESHOLD) -> pd.DataFrame:
    """ROI per division, market and price set, at one edge threshold."""
    if bets.empty:
        return pd.DataFrame()
    picked = bets[bets["edge"] >= threshold]
    if picked.empty:
        return pd.DataFrame()
    out = []
    keys = ["division", "price_set", "market"]
    for (division, price_set, market), group in picked.groupby(keys, sort=True):
        low, high, above = bootstrap_interval(group)
        out.append(
            {
                "division": division,
                "price_set": price_set,
                "market": market,
                "bets": len(group),
                "matches": group.groupby(["date", "home_team", "away_team"]).ngroups,
                "staked": float(len(group)),
                "profit": float(group["profit"].sum()),
                "roi_pct": float(group["profit"].mean() * 100.0),
                "ci_low": low,
                "ci_high": high,
                "p_above_zero": above,
            }
        )
    return pd.DataFrame(out)


def threshold_sweep(bets: pd.DataFrame) -> pd.DataFrame:
    """ROI at each edge threshold, so the headline is not the only one tried."""
    if bets.empty:
        return pd.DataFrame()
    rows = []
    for price_set in sorted(bets["price_set"].unique()):
        for threshold in EDGE_THRESHOLDS:
            picked = bets[(bets["price_set"] == price_set) & (bets["edge"] >= threshold)]
            rows.append(
                {
                    "price_set": price_set,
                    "min_edge_pct": threshold * 100.0,
                    "bets": len(picked),
                    "roi_pct": float(picked["profit"].mean() * 100.0) if len(picked) else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def calibration(bets: pd.DataFrame, *, price_set: str = "closing_average") -> pd.DataFrame:
    """What the model said would happen, beside what did.

    ROI says whether the rule loses. Calibration says *why*, and the two can
    disagree in an informative way: a model can be well calibrated and still
    lose to the vig, or badly calibrated in a region it rarely bets. Pushes are
    dropped here rather than counted as half a win — a returned stake is not
    evidence about a probability.
    """
    frame = bets[bets["price_set"] == price_set].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["won"] = frame["outcome"].map({True: 1.0, False: 0.0})
    frame = frame.dropna(subset=["won"])
    if frame.empty:
        return pd.DataFrame()
    frame["band"] = pd.cut(frame["probability"], np.arange(0.0, 1.01, 0.1))
    grouped = frame.groupby("band", observed=True).agg(
        selections=("won", "size"),
        model_pct=("probability", "mean"),
        market_pct=("price", lambda s: (1.0 / s).mean()),
        actual_pct=("won", "mean"),
    )
    for column in ("model_pct", "market_pct", "actual_pct"):
        grouped[column] = grouped[column] * 100.0
    grouped["model_error_pp"] = grouped["actual_pct"] - grouped["model_pct"]
    return grouped.reset_index()


def edge_buckets(bets: pd.DataFrame, *, price_set: str = "closing_average") -> pd.DataFrame:
    """ROI within each edge band, rather than above each threshold.

    A cumulative threshold sweep hides the shape: every bucket is contaminated
    by the ones above it. Separate bands answer the question that actually
    matters — when this model claims a bigger edge, does it do better?
    """
    frame = bets[bets["price_set"] == price_set]
    if frame.empty:
        return pd.DataFrame()
    bands = [-1.0, -0.05, 0.0, 0.03, 0.06, 0.10, 0.20, 10.0]
    labels = ["< -5%", "-5..0%", "0..3%", "3..6%", "6..10%", "10..20%", "> 20%"]
    grouped = frame.assign(band=pd.cut(frame["edge"], bands, labels=labels)).groupby(
        "band", observed=True
    )
    return pd.DataFrame(
        {
            "edge_band": [name for name, _ in grouped],
            "bets": [len(group) for _, group in grouped],
            "roi_pct": [float(group["profit"].mean() * 100.0) for _, group in grouped],
        }
    )


def render(bets: pd.DataFrame, summary: pd.DataFrame) -> str:
    """The report, written so its limits are as visible as its numbers."""
    lines: list[str] = ["# EFL backtest", ""]

    if bets.empty:
        lines += ["No bet was produced.", ""]
        return "\n".join(lines)

    closing = bets[bets["price_set"] == "closing_average"]
    headline = closing[closing["edge"] >= HEADLINE_THRESHOLD]
    low, high, above = bootstrap_interval(headline)
    roi = headline["profit"].mean() * 100.0 if len(headline) else float("nan")

    lines += [
        "## What this is",
        "",
        "A walk-forward test of the ratings model on the three EFL divisions, "
        "priced against Football-Data's own bookmaker odds. No provider credit "
        "was spent: the prices ship in the same files as the results.",
        "",
        "**This is a goals model, not the model the EPL card bets.** Understat "
        "publishes xG for six top-tier leagues and none of the EFL, and the "
        "card fits a 70/30 xG blend. Asking for the blend here would not fail — "
        "it would silently produce this same goals model, because every EFL row "
        "has empty xG. So goals were requested explicitly. No number below is "
        "comparable with an EPL number.",
        "",
        "## Headline",
        "",
        f"At the closing average price, taking every selection the model rated "
        f"at {HEADLINE_THRESHOLD * 100:.0f}% edge or better:",
        "",
        f"- **{len(headline):,} bets** across "
        f"{headline.groupby(['date', 'home_team', 'away_team']).ngroups:,} matches",
        f"- **{roi:+.2f}% ROI**, 95% interval **{low:+.2f}% to {high:+.2f}%**",
        f"- probability the true ROI is above zero: **{above:.1%}**",
        "",
    ]

    lines += ["## By division and market", "", "Closing average, edge >= "
              f"{HEADLINE_THRESHOLD * 100:.0f}%. An interval that excludes zero is a "
              "result, not a hint.", ""]
    closing_summary = summary[summary["price_set"] == "closing_average"]
    lines += ["| Division | Market | Bets | ROI | 95% interval | P(>0) |",
              "|:--|:--|--:|--:|:--|--:|"]
    for _, row in closing_summary.iterrows():
        lines.append(
            f"| {row['division']} | `{row['market']}` | {int(row['bets']):,} | "
            f"{row['roi_pct']:+.2f}% | {row['ci_low']:+.2f}% to {row['ci_high']:+.2f}% | "
            f"{row['p_above_zero']:.1%} |"
        )
    lines.append("")

    buckets = edge_buckets(bets)
    lines += [
        "## Does the model's own edge predict anything?",
        "",
        "ROI within each edge band, not above each threshold — a cumulative "
        "sweep hides the shape because every band is contaminated by the ones "
        "above it. If the edge estimate carried information, ROI would climb "
        "across these rows.",
        "",
        "| Edge band | Bets | ROI |",
        "|:--|--:|--:|",
    ]
    for _, row in buckets.iterrows():
        lines.append(f"| {row['edge_band']} | {int(row['bets']):,} | {row['roi_pct']:+.2f}% |")
    lines.append("")

    bands = calibration(bets)
    lines += [
        "## Calibration",
        "",
        "What the model said would happen, beside what did, and beside what the "
        "market said. Every candidate selection, not just the ones bet.",
        "",
        "| Model probability | Selections | Model | Market | Actual | Model error |",
        "|:--|--:|--:|--:|--:|--:|",
    ]
    for _, row in bands.iterrows():
        lines.append(
            f"| {row['band']} | {int(row['selections']):,} | {row['model_pct']:.1f}% | "
            f"{row['market_pct']:.1f}% | {row['actual_pct']:.1f}% | "
            f"{row['model_error_pp']:+.1f} pp |"
        )
    lines.append("")

    lines += ["## Coverage", "",
              "The card bets seven markets. This test could price three. A "
              "market absent from the tables above was not measured and found "
              "fine — it was not measured.", "",
              "| Card market | Measured here | Why not |", "|:--|:--|:--|"]
    for market in CARD_MARKETS:
        if market in MEASURABLE_MARKETS:
            lines.append(f"| `{market}` | yes | |")
        else:
            lines.append(f"| `{market}` | **no** | {UNPRICED_REASON[market]} |")
    lines += ["",
              "`1x2` is measured here and is *not* on the card — it is kept as a "
              "reference because it is the market Football-Data prices most "
              "completely, and because the card excluded it for losing out of "
              "sample.", ""]
    return "\n".join(lines)
