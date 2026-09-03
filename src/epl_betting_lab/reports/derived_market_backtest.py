"""Backtest the markets that actually carry the card, against real prices.

Corners are 23 of the first 42 best bets and BTTS, draw-no-bet and double
chance are most of the rest, and until 2026-09-02 not one of them had ever
been judged against money. Football-Data ships odds only for 1X2 and the 2.5
line, and this repo concluded from that — wrongly, for weeks — that no other
market could ever be profit-backtested. The provider sells all four
historically, at books Cooper can bet.

Three commitments, because each of them has already gone wrong here once:

- **The card's own rule, not a re-implementation.** Probabilities go through
  the same `evaluate_*` functions the live card calls, so what is measured is
  what is bet — calibration, shrinkage, juice cap and all.
- **Only prices Cooper could have taken.** `bettable_only` first, then the
  best remaining price. A maximum over books he cannot bet is optimistic by
  construction.
- **Walk-forward.** Every match is priced by models fitted only on matches
  played strictly before it.

What this cannot do is measure closing-line value: one snapshot per fixture at
a fixed lead means there is no close to compare against. Profit is the weaker
instrument and a season is a small sample, so read the interval, not the
point.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from epl_betting_lab.books import bettable_only
from epl_betting_lab.config import MAX_DEFAULT_JUICE, MIN_EDGE
from epl_betting_lab.models.poisson_goals import (
    BTTS_RATINGS,
    CARD_RATINGS,
    PoissonGoalsModel,
)
from epl_betting_lab.providers.team_names import normalize_team_name
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.count_markets import (
    evaluate_count_market,
    fit_count_models,
)
from epl_betting_lab.strategies.derived_result import (
    evaluate_double_chance,
    evaluate_draw_no_bet,
)

#: Provider market key -> the card's market name.
SCORE_MATRIX_MARKETS = {
    "btts": "btts",
    "draw_no_bet": "draw_no_bet",
    "double_chance": "double_chance",
}

#: Corner lines the card bets. Others are bought but not scored here.
CORNER_LINES = (9.5, 10.5)

#: Below this many prior matches the ratings are noise, not a model.
MIN_TRAINING_MATCHES = 380

#: A bet that was placed and returned the stake. It is a bet: it belongs in the
#: denominator at zero profit. Dropping pushes removed 33 of 115 draw-no-bet
#: selections and reported +7.1% for a rule that returned +5.1%.
PUSH = "push"


@dataclass
class BacktestResult:
    bets: pd.DataFrame = field(default_factory=pd.DataFrame)
    scored: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: Why rows were dropped, so an empty answer is never mistaken for a null one.
    notes: list[str] = field(default_factory=list)


def american_to_profit(american: float, won: bool) -> float:
    """Units returned by a 1-unit bet."""
    if not won:
        return -1.0
    return american / 100.0 if american > 0 else 100.0 / abs(american)


def _selection_for(market: str, name: str, home: str, away: str) -> str | None:
    """Translate a provider outcome name into the card's selection name.

    The provider names sides by club — `Bournemouth`, `Liverpool or Draw` —
    and the card names them by position. Getting this wrong would silently
    grade the home bet against the away result, so anything unrecognised
    returns None and is counted rather than guessed at.
    """
    text = str(name).strip()
    if market == "btts":
        lowered = text.casefold()
        return lowered if lowered in {"yes", "no"} else None

    home_name = normalize_team_name(home)
    away_name = normalize_team_name(away)

    if market == "draw_no_bet":
        side = normalize_team_name(text)
        if side == home_name:
            return "home"
        if side == away_name:
            return "away"
        return None

    if market == "double_chance":
        parts = [normalize_team_name(part) for part in text.split(" or ")]
        if len(parts) != 2:
            return None
        raw_parts = [part.strip().casefold() for part in text.split(" or ")]
        has_draw = "draw" in raw_parts
        sides = {part for part, raw in zip(parts, raw_parts) if raw != "draw"}
        if has_draw and home_name in sides:
            return "home_or_draw"
        if has_draw and away_name in sides:
            return "draw_or_away"
        if not has_draw and sides == {home_name, away_name}:
            return "home_or_away"
        return None

    return None


def load_bettable_prices(odds: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Best price per fixture/market/selection, among books Cooper can bet.

    Rows with no `book` are dropped, not defaulted: they predate the column
    and each carries a maximum taken across every bookmaker the provider
    returned, including ones the card may not price. `bettable_only` fails
    closed for the same reason.
    """
    notes: list[str] = []
    frame = odds.copy()
    if "book" not in frame.columns:
        return pd.DataFrame(), ["No `book` column: every price is unattributable."]

    before = len(frame)
    named = frame["book"].astype(str).str.strip()
    frame = frame[named.ne("") & named.ne("nan") & frame["book"].notna()]
    if len(frame) < before:
        notes.append(
            f"Dropped {before - len(frame)} row(s) with no book — a cross-book "
            "maximum cannot be shown to have been takeable."
        )

    before = len(frame)
    frame = bettable_only(frame)
    if len(frame) < before:
        notes.append(
            f"Dropped {before - len(frame)} row(s) priced only at books that "
            "are not on BETTABLE_BOOKS."
        )
    return frame, notes


def _prepare(odds: pd.DataFrame, matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    odds = odds.copy()
    odds["date"] = (
        pd.to_datetime(odds["commence_time"], errors="coerce", utc=True)
        .dt.tz_localize(None)
        .dt.normalize()
    )
    for column in ("home_team", "away_team"):
        odds[column] = odds[column].map(normalize_team_name)

    matches = matches.copy()
    matches["date"] = pd.to_datetime(matches["date"]).dt.normalize()
    for column in ("home_team", "away_team"):
        matches[column] = matches[column].map(normalize_team_name)
    return odds, matches.sort_values("date").reset_index(drop=True)


def _settle(market: str, selection: str, row: pd.Series) -> bool | None:
    home_goals = float(row["home_goals"])
    away_goals = float(row["away_goals"])
    if market == "btts":
        both = home_goals > 0 and away_goals > 0
        return both if selection == "yes" else not both
    if market == "draw_no_bet":
        if home_goals == away_goals:
            return PUSH  # stake returned: a bet, at zero profit
        winner = "home" if home_goals > away_goals else "away"
        return selection == winner
    if market == "double_chance":
        if selection == "home_or_draw":
            return home_goals >= away_goals
        if selection == "draw_or_away":
            return away_goals >= home_goals
        if selection == "home_or_away":
            return home_goals != away_goals
    return None


def _score_matrix_bets(
    odds: pd.DataFrame, matches: pd.DataFrame, result: BacktestResult
) -> list[dict[str, object]]:
    """Every score-matrix market, walked forward one matchday at a time."""
    rows: list[dict[str, object]] = []
    subset = odds[odds["market"].isin(SCORE_MATRIX_MARKETS)]
    if subset.empty:
        return rows

    unmapped = 0
    for match_date, day_odds in subset.groupby("date", sort=True):
        train = matches[matches["date"] < match_date]
        if len(train) < MIN_TRAINING_MATCHES:
            continue
        fixtures = (
            day_odds[["home_team", "away_team"]]
            .drop_duplicates()
            .reset_index(drop=True)
        )
        # BTTS runs on its own ratings on the live card; the derived 1X2
        # markets stay on CARD_RATINGS. Measuring them any other way would
        # measure a card that does not exist.
        card_projections = (
            PoissonGoalsModel()
            .fit(train, last_n_matches_per_team=38, config=CARD_RATINGS)
            .project_fixtures(fixtures)
        )
        btts_projections = (
            PoissonGoalsModel().fit(train, config=BTTS_RATINGS).project_fixtures(fixtures)
        )

        priced: list[dict[str, object]] = []
        for _, row in day_odds.iterrows():
            selection = _selection_for(
                str(row["market"]), row["selection"], row["home_team"], row["away_team"]
            )
            if selection is None:
                unmapped += 1
                continue
            priced.append(
                {
                    "date": match_date,
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "market": row["market"],
                    "selection": selection,
                    "american_odds": float(row["american"]),
                    "book": row["book"],
                }
            )
        if not priced:
            continue
        day_frame = pd.DataFrame(priced)
        # Best takeable price per selection, exactly as the card quotes.
        day_frame = (
            day_frame.sort_values("american_odds", ascending=False)
            .groupby(["home_team", "away_team", "market", "selection"], as_index=False)
            .first()
        )

        graded = pd.concat(
            [
                evaluate_btts(
                    btts_projections,
                    day_frame,
                    min_edge=MIN_EDGE,
                    max_juice=MAX_DEFAULT_JUICE,
                ),
                evaluate_draw_no_bet(
                    card_projections,
                    day_frame,
                    min_edge=MIN_EDGE,
                    max_juice=MAX_DEFAULT_JUICE,
                ),
                evaluate_double_chance(
                    card_projections,
                    day_frame,
                    min_edge=MIN_EDGE,
                    max_juice=MAX_DEFAULT_JUICE,
                ),
            ],
            ignore_index=True,
        )
        if graded.empty:
            continue
        graded["date"] = match_date
        rows.extend(graded.to_dict("records"))

    if unmapped:
        result.notes.append(
            f"{unmapped} provider selection(s) could not be mapped to a card "
            "selection and were skipped rather than guessed at."
        )
    return rows


def _corner_bets(odds: pd.DataFrame, matches: pd.DataFrame) -> list[dict[str, object]]:
    """Corner totals, from the count models, walked forward.

    Kept separate because corners are not a score-matrix market: they have
    their own Poisson count models and their own two lines. They still go
    through the card's own `evaluate_count_market`, so the status that decides
    whether a row is a bet is the card's, not one invented here — an earlier
    draft scored them without a status and silently dropped all 800.
    """
    subset = odds[odds["market"] == "alternate_totals_corners"].copy()
    if subset.empty:
        return []
    subset["line"] = (
        subset["selection"].astype(str).str.extract(r"@([0-9.]+)").astype(float)
    )
    subset["side"] = (
        subset["selection"].astype(str).str.extract(r"^(Over|Under)")[0].str.lower()
    )
    subset = subset[subset["line"].isin(CORNER_LINES)].dropna(subset=["side"])
    if subset.empty:
        return []
    subset["card_market"] = [
        f"corners_total_{str(line).replace('.', '_')}" for line in subset["line"]
    ]

    rows: list[dict[str, object]] = []
    for match_date, day_odds in subset.groupby("date", sort=True):
        train = matches[matches["date"] < match_date]
        if len(train) < MIN_TRAINING_MATCHES:
            continue
        models = fit_count_models(train)
        if "corners" not in models:
            continue
        best = (
            day_odds.sort_values("american", ascending=False)
            .groupby(["home_team", "away_team", "card_market", "side"], as_index=False)
            .first()
        )
        # Build the card's odds frame explicitly. Renaming onto `market` and
        # `selection` left the provider's own columns of those names in place,
        # and pandas cannot index a frame with duplicate labels.
        priced = pd.DataFrame(
            {
                "home_team": best["home_team"].to_numpy(),
                "away_team": best["away_team"].to_numpy(),
                "market": best["card_market"].to_numpy(),
                "selection": best["side"].to_numpy(),
                "american_odds": best["american"].to_numpy(),
                "book": best["book"].to_numpy(),
            }
        )
        fixtures = priced[["home_team", "away_team"]].drop_duplicates()
        for market in sorted(priced["market"].unique()):
            graded = evaluate_count_market(
                market,
                models,
                fixtures,
                priced,
                min_edge=MIN_EDGE,
                max_juice=MAX_DEFAULT_JUICE,
            )
            if graded.empty:
                continue
            graded["date"] = match_date
            graded["line"] = float(market.rsplit("_", 2)[-2] + "." + market.rsplit("_", 1)[-1])
            rows.extend(graded.to_dict("records"))
    return rows


def _settle_corner(row: pd.Series, match: pd.Series) -> bool | str | None:
    """None means the match cannot be settled at all; PUSH means it landed on
    the line. Conflating the two hid both."""
    if pd.isna(match.get("HC")) or pd.isna(match.get("AC")):
        return None
    total = float(match["HC"]) + float(match["AC"])
    line = float(row["line"])
    if total == line:
        return PUSH
    return total > line if row["selection"] == "over" else total < line


def _require_xg(matches: pd.DataFrame) -> None:
    """Refuse to measure BTTS on a model the card does not bet.

    `BTTS_RATINGS` asks for a 70/30 xG blend, and `PoissonGoalsModel` quietly
    serves pure goals when `home_xg`/`away_xg` are missing. Passing
    `load_matches()` therefore measured a different model and said so nowhere:
    BTTS reported -1.5% where the rule the card actually bets returned -10.6%.
    A docstring promising "what is measured is what is bet" has to be enforced,
    not asserted.
    """
    if matches.empty:
        return
    missing = [c for c in ("home_xg", "away_xg") if c not in matches.columns]
    if missing:
        raise ValueError(
            "The matches frame has no "
            f"{' or '.join(missing)}, so BTTS would be fitted on goals rather "
            "than the xG blend the live card bets. Load it with "
            "`load_matches_with_xg()`."
        )


def build_backtest(odds: pd.DataFrame, matches: pd.DataFrame) -> BacktestResult:
    """Score every card-rule bet these prices would have produced."""
    result = BacktestResult()
    _require_xg(matches)
    prices, notes = load_bettable_prices(odds)
    result.notes.extend(notes)
    if prices.empty:
        result.notes.append("No takeable prices; nothing to measure.")
        return result

    prices, matches = _prepare(prices, matches)
    played = matches.dropna(subset=["home_goals", "away_goals"])
    key = ["date", "home_team", "away_team"]
    lookup = played.set_index(key)

    candidates = _score_matrix_bets(prices, played, result) + _corner_bets(
        prices, played
    )
    if not candidates:
        result.notes.append("No fixture had enough prior matches to fit a model.")
        return result

    scored: list[dict[str, object]] = []
    unjoined = 0
    unsettleable = 0
    for row in candidates:
        index = (row["date"], row["home_team"], row["away_team"])
        if index not in lookup.index:
            unjoined += 1
            continue
        match = lookup.loc[index]
        if isinstance(match, pd.DataFrame):
            match = match.iloc[0]
        if str(row["market"]).startswith("corners_"):
            won = _settle_corner(pd.Series(row), match)
        else:
            won = _settle(str(row["market"]), str(row["selection"]), match)
        if won is None:
            unsettleable += 1
            continue
        scored.append(
            {
                **row,
                "won": False if won is PUSH else bool(won),
                "push": won is PUSH,
            }
        )

    if unsettleable:
        result.notes.append(
            f"{unsettleable} selection(s) could not be settled at all (no "
            "corner counts on the result row) and were dropped. Counted here "
            "because an uncounted drop is indistinguishable from a bet that "
            "was never placed."
        )
    if unjoined:
        result.notes.append(
            f"{unjoined} priced selection(s) had no matching result and were "
            "dropped. Team-name spelling is the usual cause."
        )
    if not scored:
        result.notes.append("Nothing settled.")
        return result

    frame = pd.DataFrame(scored)
    frame["profit"] = [
        0.0 if bool(p) else american_to_profit(float(a), bool(w))
        for a, w, p in zip(frame["american_odds"], frame["won"], frame["push"])
    ]
    result.scored = frame
    # The card bets a row only when its calibrated status says so. Reading the
    # status is what makes this the card's rule rather than a rule of mine.
    if "status" in frame.columns:
        result.bets = frame[frame["status"].astype(str).str.upper() == "BETTABLE"].copy()
    else:
        result.bets = frame.copy()
    return result


def bootstrap_interval(
    bets: pd.DataFrame, *, draws: int = 2000, seed: int = 12345
) -> tuple[float, float, float]:
    """95% interval for ROI, resampling whole matches.

    Selections on the same match share a result, so resampling rows would
    treat correlated bets as independent and report an interval that is too
    narrow.
    """
    if bets.empty:
        return (float("nan"), float("nan"), float("nan"))
    groups = [
        group["profit"].to_numpy()
        for _, group in bets.groupby(["date", "home_team", "away_team"], sort=True)
    ]
    rng = np.random.default_rng(seed)
    rois = np.empty(draws)
    count = len(groups)
    for draw in range(draws):
        picked = rng.integers(0, count, count)
        profits = np.concatenate([groups[index] for index in picked])
        rois[draw] = profits.mean() * 100.0
    return (
        float(np.percentile(rois, 2.5)),
        float(np.percentile(rois, 97.5)),
        float((rois > 0).mean()),
    )


def summarize(result: BacktestResult) -> pd.DataFrame:
    """Per-market bets, ROI and interval. One row per market, plus ALL."""
    if result.bets.empty:
        return pd.DataFrame()
    rows = []
    for market, group in list(result.bets.groupby("market", sort=True)) + [
        ("ALL", result.bets)
    ]:
        low, high, above_zero = bootstrap_interval(group)
        rows.append(
            {
                "market": market,
                "bets": len(group),
                "pushes": int(group["push"].sum()),
                "win_rate": round(float(group["won"].mean()) * 100, 1),
                "units": round(float(group["profit"].sum()), 2),
                "roi_pct": round(float(group["profit"].mean()) * 100, 2),
                "ci_low_pct": round(low, 1),
                "ci_high_pct": round(high, 1),
                "p_above_zero": round(above_zero, 2),
            }
        )
    return pd.DataFrame(rows)


def render(result: BacktestResult, summary: pd.DataFrame) -> str:
    """A report that cannot be read as proof of an edge it does not have."""
    lines = [
        "# Derived market backtest",
        "",
        "The first time corners, BTTS, draw-no-bet and double chance have been "
        "judged against prices that were really offered, at books that can "
        "really be bet.",
        "",
        "One snapshot per fixture at a fixed lead before kick-off, so there is "
        "**no closing line here and no CLV** — only profit, which is the weaker "
        "instrument. Read the interval, not the point estimate: an interval "
        "that includes zero has not demonstrated an edge, whatever the ROI says.",
        "",
        "`pushes` are bets that returned the stake — a drawn draw-no-bet, a "
        "corner total landing on the line. They are bets, so they sit in the "
        "denominator at zero profit; dropping them once removed 33 of 115 "
        "draw-no-bet selections and reported +7.1% for a rule that returned "
        "+5.1%. `win_rate` is therefore over all bets, pushes included.",
        "",
    ]
    if summary.empty:
        lines.append("No bets were produced.")
    else:
        lines.append(summary.to_markdown(index=False))
        lines.append("")
        lines.append(
            f"Scored candidates: {len(result.scored)}. "
            f"Bets the card rule would have taken: {len(result.bets)}."
        )
    if result.notes:
        lines.extend(["", "## What was dropped, and why", ""])
        lines.extend(f"- {note}" for note in result.notes)
    return "\n".join(lines) + "\n"
