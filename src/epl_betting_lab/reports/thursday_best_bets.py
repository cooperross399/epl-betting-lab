from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MIN_EDGE
from epl_betting_lab.models.calibration import min_calibrated_edge
from epl_betting_lab.models.value import fair_american_from_prob

from epl_betting_lab.config import BANKROLL_UNIT_DOLLARS, MAX_DEFAULT_JUICE, OUTPUTS_DIR


REPORT_COLUMNS = [
    "section",
    "home_team",
    "away_team",
    "market",
    "selection",
    "status",
    "raw_model_prob",
    "calibrated_model_prob",
    "raw_edge",
    "calibrated_edge",
    "ranking_score",
    "confidence_tier",
    "fair_american",
    "american_odds",
    "bet_down_to_american",
    "suggested_units",
    "suggested_wager_$",
    "book",
    "risk_flags",
    "market_reliability_note",
    "qualifies_reason",
    "ranking_reason",
    "totals_note",
    "notes",
    # The market-anchored 2.5 rule. Blank for every other market. These are
    # what forward CLV tracking needs to tell an anchored bet from the rest,
    # and what the stake cap in _confidence_tier reads.
    "selection_rule",
    "market_prob",
    "market_prob_source",
    "anchor_lift",
]

ARCHIVE_COLUMNS = [
    "generated_at",
    "validation_status",
    "best_bets",
    "leans",
    "passes",
    "markdown",
    "csv",
    "metadata",
]


def missing_current_odds_message(path: Path) -> str:
    return (
        f"Missing {path}. Copy data/manual/current_odds_template.csv to "
        f"data/manual/current_odds.csv by running `cp data/manual/current_odds_template.csv "
        f"data/manual/current_odds.csv`, then enter real sportsbook odds before running "
        f"the Thursday best-bets report."
    )


def _value(row: pd.Series, column: str, fallback: object = pd.NA) -> object:
    if column not in row or pd.isna(row[column]):
        return fallback
    return row[column]


def _float_value(row: pd.Series, column: str, fallback: float = 0.0) -> float:
    value = _value(row, column, fallback)
    numeric = pd.to_numeric(value, errors="coerce")
    return fallback if pd.isna(numeric) else float(numeric)


#: A market needs at least this many settled bets before its measured return
#: may nudge the ranking at all.
#:
#: Not a significance threshold — CLAUDE.md's own arithmetic puts that near
#: 1,500 bets — but a floor below which a number is plainly noise. `total_2_5`
#: was drawing the maximum +12 adjustment from FIVE backtested bets at +40.8%.
MINIMUM_BETS_FOR_MARKET_RELIABILITY = 200


def _market_reliability_from_backtest(path: Path | None = None) -> dict[str, float]:
    """Measured per-market return, as points on the 0-100 ranking score.

    Empty in practice, and the emptiness is the point.

    This read `backtest_market_breakdown.csv` and scaled each market's ROI by
    50 into a +/-12 band. Three things were wrong with that at once. The
    `total_2_5` row is five bets at +40.8%, which pinned the maximum bonus to
    the noisiest number in the file. The `1x2` row is the +34.41 units over 502
    bets that `docs/no_edge_out_of_sample.md` repudiates — profit produced by a
    calibration filter tuned on the very pass it was scored on, and negative on
    every held-out season. And the file is an IN-SAMPLE backtest whichever row
    you read, so no row in it can justify moving a live ranking.

    Meanwhile the markets that actually carry the card got nothing: corners are
    23 of the first 42 best bets, with draw_no_bet and double_chance another
    12, and none of the five appears in the file at all. So the ranking was
    being nudged for markets that barely reach the card and left alone for the
    ones that dominate it.

    The mechanism stays — `build_thursday_best_bets` still takes an override,
    and `MINIMUM_BETS_FOR_MARKET_RELIABILITY` is here for the day a forward
    record earns one. The forward record is the only honest source, and at 33
    settled selections it is nowhere near able to fill this. Until then every
    market is treated alike, which is what "we do not know" looks like.
    """
    return {}


def _notes_for_totals(row: pd.Series) -> str:
    if row.get("market") != "total_2_5":
        return ""
    notes = []
    if bool(row.get("goal_environment_under_guardrail", False)):
        notes.append("Under guardrail triggered: recent goal environment looked hot.")
    reason = _value(row, "goal_environment_reason", "")
    if reason:
        notes.append(str(reason))
    pre_status = _value(row, "pre_goal_environment_calibrated_status", "")
    if pre_status:
        notes.append(f"Pre-adjustment status: {pre_status}.")
    return " ".join(notes)


def _qualifies_reason(row: pd.Series, section: str) -> str:
    status = str(row["status"])
    if section == "Best bets":
        return f"Calibrated status is {status} with positive calibrated edge, playable price, and {row['confidence_tier']}-tier ranking."
    if section == "Leans":
        return "Positive but thinner edge; keep smaller unless the price improves."
    if "too much juice" in status.lower():
        return "Avoid: price is worse than the default max-juice rule around -160."
    if "hot goal environment" in status.lower():
        return "Avoid: totals under protection flagged a hot goal environment."
    if "pre-adjustment edge" in status.lower():
        return "Avoid: totals needed stronger edge before goal-environment adjustment."
    return f"Pass: calibrated status is {status}."


def _market_reliability_note(row: pd.Series, market_reliability: dict[str, float]) -> str:
    market = str(row.get("market", ""))
    adjustment = market_reliability.get(market, 0.0)
    if market == "1x2":
        trust = "1X2 is currently the most trusted market in this report."
    elif market == "total_2_5":
        trust = "Totals are treated cautiously because recent backtests showed leakage."
    elif market == "btts":
        trust = "BTTS is allowed, but ranked between 1X2 and totals until more evidence builds."
    else:
        trust = "Market reliability is neutral."
    return f"{trust} Reliability adjustment: {adjustment:+.1f} points."


def _risk_flags(row: pd.Series) -> str:
    flags = []
    market = str(row.get("market", ""))
    selection = str(row.get("selection", "")).lower()
    odds = _float_value(row, "american_odds")
    if odds <= MAX_DEFAULT_JUICE:
        flags.append("heavy juice")
    if odds > 100:
        flags.append("plus-money variance")
    if market == "total_2_5":
        flags.append("totals market caution")
    if market == "total_2_5" and selection == "under":
        flags.append("totals under caution")
    if bool(row.get("goal_environment_under_guardrail", False)):
        flags.append("goal-environment under guardrail")
    return "; ".join(flags)


def _ranking_components(row: pd.Series, market_reliability: dict[str, float]) -> tuple[float, list[str]]:
    market = str(row.get("market", ""))
    selection = str(row.get("selection", "")).lower()
    status = str(row.get("status", ""))
    status_upper = status.upper()
    odds = _float_value(row, "american_odds")
    calibrated_edge = _float_value(row, "calibrated_edge", _float_value(row, "edge"))
    calibrated_prob = _float_value(row, "calibrated_model_prob", _float_value(row, "model_prob"))

    score = 0.0
    reasons: list[str] = []

    edge_points = max(0.0, min(40.0, calibrated_edge * 500))
    prob_points = max(0.0, min(15.0, calibrated_prob * 22))
    score += edge_points + prob_points
    reasons.append(f"calibrated edge adds {edge_points:.1f}")
    reasons.append(f"calibrated probability adds {prob_points:.1f}")

    if status_upper == "BETTABLE":
        score += 15.0
        reasons.append("BETTABLE status adds 15.0")
    elif status_upper == "LEAN":
        score += 5.0
        reasons.append("LEAN status adds 5.0")
    else:
        score -= 25.0
        reasons.append("PASS/Avoid status subtracts 25.0")

    reliability = market_reliability.get(market, 0.0)
    score += reliability
    reasons.append(f"market reliability adds {reliability:+.1f}")

    if odds <= MAX_DEFAULT_JUICE:
        score -= 15.0
        reasons.append(f"heavy juice {int(odds):+d} subtracts 15.0")
    if odds > 100:
        score -= 4.0
        reasons.append("plus-money variance subtracts 4.0")

    if market == "total_2_5":
        score -= 8.0
        reasons.append("totals caution subtracts 8.0")
        if selection == "under":
            score -= 12.0
            reasons.append("totals under caution subtracts 12.0")
        if bool(row.get("goal_environment_under_guardrail", False)):
            score -= 15.0
            reasons.append("goal-environment under guardrail subtracts 15.0")

    return round(max(0.0, min(100.0, score)), 1), reasons


#: Leans are shown and not staked. The card already separates zero-unit rows
#: under "Ranked but not stakeable", so this needs no new presentation — a lean
#: simply stops arriving with a stake attached to it.
LEAN_TIER = "Lean (no stake)"


#: Markets a bet rule can be profit-backtested on, because a historical price
#: source exists. Football-Data ships odds for these two and nothing else, and
#: the bought provider history covers props and corner totals only.
PROFIT_BACKTESTABLE_MARKETS: frozenset[str] = frozenset({"1x2", "total_2_5"})

#: The stake for a market whose profit can never be verified: the smallest one.
#:
#: This was written as "one tier down, not a floor - the ranking still says
#: which of these are better than the others". That claim was false the moment
#: it shipped, and the numbers were there to check it. Of the markets the card
#: can stake, only `total_2_5` is profit-backtestable, and it is separately
#: capped at C by the anchored rule. Every other market steps down. Across the
#: first 162 archived best bets the card issued B 69 times and C 93 times and A
#: never once - so "one tier down" from an unreachable A is B->C, and every
#: stakeable row lands on C. It is a floor. Saying otherwise made the card
#: print eight rows of "C" while the commit message claimed the ranking still
#: moved the stake.
#:
#: So it is a floor, deliberately and in the open. Nothing on this card has a
#: demonstrated edge; the honest position is that every bet is the same small
#: size until the forward record says one of them deserves more.
#:
#: NOT a calibration judgement. The corner models are well calibrated - gaps of
#: -0.0, 0.0 and 0.0 points over 924 and 616 walk-forward predictions - and
#: BTTS's bias has been measured out. The reason is narrower: for these markets
#: no historical price exists at any source, so no rule on them can ever be
#: shown to make money however well the probabilities are calibrated.
#:
#: The tier is still computed and still shown, because it orders the card and
#: says which bets the model likes most. It just no longer changes the stake,
#: and the card now says so rather than leaving a column of Cs to be puzzled
#: over. Reversible: `data/outputs/live_clv_report.md` is where a market earns
#: its way back to a bigger stake.
UNVERIFIABLE_MARKET_TIER = "C"


#: The shortest price at which a pick is still worth taking.
#:
#: Named for the convention Cooper's golf cards already use — model fair odds
#: quoted with a "bet down to" threshold. A card that only shows the price at
#: one book at one moment answers the wrong question: by the time he looks, the
#: line has usually moved. What he needs is the number it stops being a bet at.
#:
#: It is NOT the fair price. Fair is break-even — zero edge — and taking a bet
#: at fair is taking a coin flip with the vig still to pay. The limit is the
#: price at which the edge falls to the bar this market has to clear, which is
#: strictly longer than fair. Cross it and the bet is off, not marginal.
def _bet_down_to(row: pd.Series) -> float | str:
    market = str(row.get("market", "")).strip()
    selection = str(row.get("selection", "")).strip().lower()
    probability = _float_value(row, "calibrated_model_prob", _float_value(row, "model_prob"))
    if not probability or not 0 < probability < 1:
        return ""
    floor = min_calibrated_edge(market, selection, MIN_EDGE)
    # A stake is only advised while edge >= floor, so implied must not exceed
    # probability - floor. Above that the price has stopped paying for the risk.
    limit = probability - floor
    if limit <= 0 or limit >= 1:
        return ""
    return round(fair_american_from_prob(limit))


def _confidence_tier(row: pd.Series) -> str:
    section = row.get("section")
    status = str(row.get("status", "")).upper()
    market = str(row.get("market", ""))
    selection = str(row.get("selection", "")).lower()
    score = _float_value(row, "ranking_score")
    edge = _float_value(row, "calibrated_edge", _float_value(row, "edge"))

    if section == "Passes / notable avoids" or "PASS" in status or edge <= 0:
        return "Pass/Avoid"
    if status == "LEAN":
        # A lean is information, not a bet. It fires at a 1.5% modelled edge,
        # which is smaller than this model's own demonstrated error — the
        # calibration work found it off by four to fifteen points depending on
        # the band — and smaller than a typical book margin of four to six per
        # cent. A threshold below the noise floor cannot be selecting for skill.
        #
        # Measured: 1X2 leans returned -18.6% over 65 bets, positive in one
        # season of four; BTTS leans -1.0% over 85. Combined, 150 bets at -8.6%.
        # Not significant on its own, and pointing the same way as the reason
        # to expect it.
        return LEAN_TIER
    if score >= 72:
        tier = "A"
    elif score >= 55:
        tier = "B"
    elif score >= 35:
        tier = "C"
    else:
        tier = "Pass/Avoid"
    if market == "total_2_5" and selection == "under" and tier == "A":
        tier = "B"
    # The market-anchored 2.5 rule has no demonstrated edge — held out by
    # season it sits at zero CLV — so it is tracked forward at the smallest
    # stake the card uses, whatever its ranking score says. Raising this is a
    # decision for the CLV record to earn, not for a score to grant.
    if str(row.get("selection_rule", "")) == "market_anchored" and tier in {"A", "B"}:
        return "C"
    if market and market not in PROFIT_BACKTESTABLE_MARKETS and tier in {"A", "B"}:
        return UNVERIFIABLE_MARKET_TIER
    return tier


def _suggested_units(tier: str) -> float:
    return {
        "A": 0.5,
        "B": 0.25,
        "C": 0.1,
        LEAN_TIER: 0.0,
        "Pass/Avoid": 0.0,
    }.get(tier, 0.0)


def _section(status: object) -> str:
    status_text = "" if pd.isna(status) else str(status)
    if status_text == "BETTABLE":
        return "Best bets"
    if status_text == "LEAN":
        return "Leans"
    return "Passes / notable avoids"


def build_thursday_best_bets(
    candidates: pd.DataFrame,
    max_best_bets: int = 8,
    max_passes: int = 12,
    market_reliability: dict[str, float] | None = None,
) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame(columns=REPORT_COLUMNS)

    df = candidates.copy()
    if "status" not in df.columns:
        return pd.DataFrame(columns=REPORT_COLUMNS)
    df["section"] = df["status"].apply(_section)
    df["raw_model_prob"] = df.apply(lambda row: _value(row, "raw_model_prob", _value(row, "model_prob")), axis=1)
    df["calibrated_model_prob"] = df.apply(
        lambda row: _value(row, "calibrated_model_prob", _value(row, "model_prob")),
        axis=1,
    )
    df["raw_edge"] = df.apply(lambda row: _value(row, "raw_edge", _value(row, "edge")), axis=1)
    df["calibrated_edge"] = df.apply(lambda row: _value(row, "calibrated_edge", _value(row, "edge")), axis=1)
    df["book"] = df.apply(lambda row: _value(row, "book", ""), axis=1)
    df["notes"] = df.apply(lambda row: _value(row, "notes", ""), axis=1)
    df["totals_note"] = df.apply(_notes_for_totals, axis=1)
    market_reliability = market_reliability or _market_reliability_from_backtest()
    scores_and_reasons = df.apply(lambda row: _ranking_components(row, market_reliability), axis=1)
    df["ranking_score"] = scores_and_reasons.apply(lambda item: item[0])
    df["ranking_reason"] = scores_and_reasons.apply(lambda item: "; ".join(item[1]))
    df["bet_down_to_american"] = df.apply(_bet_down_to, axis=1)
    df["confidence_tier"] = df.apply(_confidence_tier, axis=1)
    df["risk_flags"] = df.apply(_risk_flags, axis=1)
    df["market_reliability_note"] = df.apply(lambda row: _market_reliability_note(row, market_reliability), axis=1)
    df["qualifies_reason"] = df.apply(lambda row: _qualifies_reason(row, row["section"]), axis=1)
    df["suggested_units"] = df["confidence_tier"].apply(_suggested_units)
    # Only the anchored 2.5 rule carries these; every other market's rows are
    # blank for them rather than absent, so the column selection below holds.
    for column in ("selection_rule", "market_prob", "market_prob_source", "anchor_lift"):
        if column not in df.columns:
            df[column] = pd.NA
    df["suggested_wager_$"] = (df["suggested_units"] * BANKROLL_UNIT_DOLLARS).round(2)

    best = df[df["section"] == "Best bets"].sort_values(["ranking_score", "calibrated_edge"], ascending=False).head(max_best_bets)
    leans = df[df["section"] == "Leans"].sort_values(["ranking_score", "calibrated_edge"], ascending=False)
    passes = df[df["section"] == "Passes / notable avoids"].sort_values(["ranking_score", "calibrated_edge"], ascending=False).head(max_passes)
    report = pd.concat([best, leans, passes], ignore_index=True)
    return report[REPORT_COLUMNS]


def _validation_warning(validation_issues: pd.DataFrame | None, forced: bool = False) -> list[str]:
    if validation_issues is None or validation_issues.empty or "severity" not in validation_issues.columns:
        return []
    serious = validation_issues[validation_issues["severity"] == "error"]
    if serious.empty:
        return []
    prefix = "Generated with `--force` despite" if forced else "`data/manual/current_odds.csv` has"
    return [
        "## Current odds validation warning",
        "",
        f"{prefix} {len(serious)} serious validation issue(s). Run `python scripts/validate_current_odds.py` and fix serious issues before trusting this card.",
        "",
    ]


def render_thursday_best_bets(
    report: pd.DataFrame,
    validation_issues: pd.DataFrame | None = None,
    forced: bool = False,
) -> str:
    lines = [
        "# EPL Thursday Best Bets Report",
        "",
        "This report uses only the manual odds in `data/manual/current_odds.csv`. It does not fetch live odds, fabricate prices, or place bets.",
        "",
        "## Wednesday/Thursday checklist",
        "",
        "1. Copy `data/manual/current_odds_template.csv` to `data/manual/current_odds.csv` if needed.",
        "2. Enter real sportsbook prices in `american_odds` and the book name in `book`.",
        "3. Leave `closing_american_odds` blank until after the market closes.",
        "4. Run `python scripts/generate_thursday_best_bets.py`.",
        "5. Review best bets, leans, and passes before deciding manually.",
        "",
        "## Ranking and confidence guide",
        "",
        "The ranking score is a transparent 0-100 helper for sorting candidates. It rewards calibrated edge, calibrated probability, BETTABLE status, and historically stronger markets. It penalizes totals, totals unders, goal-environment under warnings, heavy juice worse than about -160, plus-money variance, and pass/avoid statuses.",
        "",
        "- A: strongest best-bet profile, suggested up to 0.5u.",
        "- B: playable but not top tier, suggested 0.25u.",
        "- C: lean/watchlist only, suggested 0.10u max.",
        "- Pass/Avoid: no bet, suggested 0u.",
        "",
        "Totals unders cannot receive A-tier in this conservative version because they have been a historical leak; the report can still show them as B/C only when the existing protections leave them playable.",
        "",
    ]
    lines.extend(_validation_warning(validation_issues, forced=forced))
    if report.empty:
        lines.extend([
            "No candidate plays were produced from the current odds file.",
            "",
            "Check that upcoming fixtures and current odds use matching home/away team names.",
        ])
        return "\n".join(lines)

    for section in ["Best bets", "Leans", "Passes / notable avoids"]:
        subset = report[report["section"] == section]
        lines.extend([f"## {section}", ""])
        if subset.empty:
            lines.extend(["No rows in this section.", ""])
            continue
        for _, row in subset.iterrows():
            matchup = f"{row['home_team']} vs {row['away_team']}"
            price = int(float(row["american_odds"]))
            fair = int(float(row["fair_american"]))
            lines.append(f"### {matchup}")
            lines.append(f"- Play: {row['market']} {row['selection']} at {price:+d}")
            lines.append(f"- Status: {row['status']}")
            lines.append(f"- Confidence tier: {row['confidence_tier']} | Ranking score: {float(row['ranking_score']):.1f}/100")
            lines.append(f"- Suggested size: {row['suggested_units']}u")
            lines.append(
                f"- Probability: raw {float(row['raw_model_prob']):.1%}, "
                f"calibrated {float(row['calibrated_model_prob']):.1%}"
            )
            lines.append(
                f"- Edge: raw {float(row['raw_edge']):.1%}, "
                f"calibrated {float(row['calibrated_edge']):.1%}"
            )
            lines.append(f"- Fair price: {fair:+d}")
            if row["book"]:
                lines.append(f"- Book: {row['book']}")
            lines.append(f"- Why: {row['qualifies_reason']}")
            lines.append(f"- Ranking notes: {row['ranking_reason']}")
            lines.append(f"- Market reliability: {row['market_reliability_note']}")
            if row["risk_flags"]:
                lines.append(f"- Risk flags: {row['risk_flags']}")
            if row["totals_note"]:
                lines.append(f"- Totals note: {row['totals_note']}")
            if row["notes"]:
                lines.append(f"- Notes: {row['notes']}")
            lines.append("")
    return "\n".join(lines)


def _archive_generated_at(generated_at: datetime | None = None) -> tuple[datetime, str, str]:
    timestamp = generated_at or datetime.now()
    return timestamp, timestamp.strftime("%Y-%m-%d"), timestamp.strftime("%H%M%S")


def _validation_status(validation_issues: pd.DataFrame | None) -> str:
    if validation_issues is None:
        return "not_checked"
    if validation_issues.empty or "severity" not in validation_issues.columns:
        return "ready"
    severities = validation_issues["severity"].astype(str).str.lower()
    if (severities == "error").any():
        return "blocked"
    if (severities == "warning").any():
        return "warnings_only"
    return "ready"


def _section_count(report: pd.DataFrame, section: str) -> int:
    if report.empty or "section" not in report.columns:
        return 0
    return int((report["section"] == section).sum())


def _archive_paths(
    output_dir: Path,
    generated_at: datetime | None = None,
    overwrite: bool = False,
) -> tuple[datetime, dict[str, Path], str]:
    timestamp, date_label, time_label = _archive_generated_at(generated_at)
    archive_dir = output_dir / "archive" / "thursday_best_bets" / date_label
    archive_dir.mkdir(parents=True, exist_ok=True)

    suffix = ""
    while True:
        stem = f"{time_label}{suffix}_thursday_best_bets"
        paths = {
            "archive_csv": archive_dir / f"{stem}.csv",
            "archive_markdown": archive_dir / f"{stem}.md",
            "archive_metadata": archive_dir / f"{stem}_metadata.json",
        }
        if overwrite or not any(path.exists() for path in paths.values()):
            return timestamp, paths, suffix
        suffix = "_2" if not suffix else f"_{int(suffix.strip('_')) + 1}"


def archive_thursday_best_bets(
    report: pd.DataFrame,
    markdown: str,
    output_dir: Path,
    validation_issues: pd.DataFrame | None = None,
    forced: bool = False,
    generated_at: datetime | None = None,
    overwrite: bool = False,
) -> dict[str, Path]:
    timestamp, paths, _ = _archive_paths(output_dir, generated_at=generated_at, overwrite=overwrite)
    report.to_csv(paths["archive_csv"], index=False)
    paths["archive_markdown"].write_text(markdown, encoding="utf-8")

    metadata = {
        "generated_at": timestamp.isoformat(timespec="seconds"),
        "best_bets": _section_count(report, "Best bets"),
        "leans": _section_count(report, "Leans"),
        "passes": _section_count(report, "Passes / notable avoids"),
        "validation_status": _validation_status(validation_issues),
        "forced": bool(forced),
        "csv": str(paths["archive_csv"]),
        "markdown": str(paths["archive_markdown"]),
    }
    paths["archive_metadata"].write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return paths


def list_recent_thursday_archives(output_dir: Path | None = None, limit: int = 8) -> pd.DataFrame:
    output_dir = output_dir or OUTPUTS_DIR
    archive_root = output_dir / "archive" / "thursday_best_bets"
    if not archive_root.exists():
        return pd.DataFrame(columns=ARCHIVE_COLUMNS)

    rows = []
    for metadata_path in archive_root.glob("*/*_metadata.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append({
            "generated_at": metadata.get("generated_at", ""),
            "validation_status": metadata.get("validation_status", ""),
            "best_bets": metadata.get("best_bets", 0),
            "leans": metadata.get("leans", 0),
            "passes": metadata.get("passes", 0),
            "markdown": metadata.get("markdown", ""),
            "csv": metadata.get("csv", ""),
            "metadata": str(metadata_path),
        })

    if not rows:
        return pd.DataFrame(columns=ARCHIVE_COLUMNS)
    archives = pd.DataFrame(rows, columns=ARCHIVE_COLUMNS)
    return archives.sort_values("generated_at", ascending=False).head(limit).reset_index(drop=True)


def save_thursday_best_bets(
    report: pd.DataFrame,
    output_dir: Path,
    validation_issues: pd.DataFrame | None = None,
    forced: bool = False,
    archive: bool = True,
    generated_at: datetime | None = None,
    overwrite_archive: bool = False,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "thursday_best_bets.csv"
    markdown_path = output_dir / "thursday_best_bets.md"
    markdown = render_thursday_best_bets(report, validation_issues=validation_issues, forced=forced)
    report.to_csv(csv_path, index=False)
    markdown_path.write_text(markdown, encoding="utf-8")
    paths = {"csv": csv_path, "markdown": markdown_path}
    if archive:
        paths.update(
            archive_thursday_best_bets(
                report,
                markdown,
                output_dir,
                validation_issues=validation_issues,
                forced=forced,
                generated_at=generated_at,
                overwrite=overwrite_archive,
            )
        )
    return paths
