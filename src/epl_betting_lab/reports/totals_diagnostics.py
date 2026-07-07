from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.backtest_bias import edge_bucket, odds_range


TOTALS_SUMMARY_COLUMNS = [
    "candidates",
    "raw_bets",
    "raw_wins",
    "raw_profit_units",
    "raw_roi",
    "generic_calibrated_bets",
    "generic_calibrated_wins",
    "generic_calibrated_profit_units",
    "generic_calibrated_roi",
    "calibrated_bets",
    "calibrated_wins",
    "calibrated_profit_units",
    "calibrated_roi",
    "goal_environment_adjusted_bets",
    "goal_environment_adjusted_wins",
    "goal_environment_adjusted_profit_units",
    "goal_environment_adjusted_roi",
    "bets_filtered_out",
    "goal_environment_bets_filtered_out",
    "avg_american_odds",
    "avg_raw_edge",
    "avg_calibrated_edge",
    "avg_goal_environment_adjusted_edge",
    "avg_projected_total_goals",
    "avg_adjusted_projected_total_goals",
    "avg_actual_total_goals",
    "actual_over_2_5_rate",
]


def projected_goal_bucket(projected_total: float) -> str:
    if pd.isna(projected_total):
        return "unknown"
    total = float(projected_total)
    if total < 2.2:
        return "under 2.2"
    if total < 2.5:
        return "2.2 to 2.49"
    if total < 2.8:
        return "2.5 to 2.79"
    if total < 3.1:
        return "2.8 to 3.09"
    return "3.1 or higher"


def favorite_strength_bucket(strength: float) -> str:
    if pd.isna(strength):
        return "unknown"
    value = float(strength)
    if value < 0.45:
        return "no clear favorite"
    if value < 0.55:
        return "moderate favorite"
    if value < 0.65:
        return "strong favorite"
    return "heavy favorite"


def total_price_bucket(american_odds: float) -> str:
    odds = float(american_odds)
    if odds < 0:
        return "juiced total"
    if odds == 100:
        return "even-money total"
    return "plus-money total"


def _event_bucket(avg_total_goals: float, over_rate: float) -> str:
    if avg_total_goals >= 2.9 or over_rate >= 0.58:
        return "high-event team"
    if avg_total_goals <= 2.5 or over_rate <= 0.47:
        return "low-event team"
    return "neutral-event team"


def build_team_event_profile(matches: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["team", "team_avg_total_goals", "team_over_2_5_rate", "team_event_bucket"]
    if matches is None or matches.empty:
        return pd.DataFrame(columns=columns)

    df = matches.dropna(subset=["home_team", "away_team", "home_goals", "away_goals"]).copy()
    if df.empty:
        return pd.DataFrame(columns=columns)

    df["match_total_goals"] = pd.to_numeric(df["home_goals"], errors="coerce") + pd.to_numeric(df["away_goals"], errors="coerce")
    df = df.dropna(subset=["match_total_goals"])
    rows = []
    for _, match in df.iterrows():
        total_goals = float(match["match_total_goals"])
        over_25 = total_goals > 2.5
        rows.append({"team": match["home_team"], "match_total_goals": total_goals, "over_2_5": over_25})
        rows.append({"team": match["away_team"], "match_total_goals": total_goals, "over_2_5": over_25})

    team_rows = pd.DataFrame(rows)
    if team_rows.empty:
        return pd.DataFrame(columns=columns)

    profile = team_rows.groupby("team").agg(
        team_avg_total_goals=("match_total_goals", "mean"),
        team_over_2_5_rate=("over_2_5", "mean"),
    ).reset_index()
    profile["team_event_bucket"] = profile.apply(
        lambda r: _event_bucket(float(r["team_avg_total_goals"]), float(r["team_over_2_5_rate"])),
        axis=1,
    )
    profile["team_avg_total_goals"] = profile["team_avg_total_goals"].round(3)
    profile["team_over_2_5_rate"] = profile["team_over_2_5_rate"].round(3)
    return profile[columns]


def _match_event_profile(home_bucket: str, away_bucket: str) -> str:
    buckets = {home_bucket, away_bucket}
    if "high-event team" in buckets and "low-event team" in buckets:
        return "mixed-event teams"
    if "high-event team" in buckets:
        return "high-event teams involved"
    if buckets == {"low-event team"}:
        return "both low-event teams"
    if "low-event team" in buckets:
        return "low-event team involved"
    if buckets == {"unknown"}:
        return "unknown"
    return "neutral-event teams"


def enrich_totals_diagnostics(bets: pd.DataFrame, matches: pd.DataFrame | None = None) -> pd.DataFrame:
    if bets.empty:
        return bets.copy()

    df = bets[bets["market"] == "total_2_5"].copy()
    if df.empty:
        return df

    defaults = {
        "raw_edge": "edge",
        "calibrated_edge": "edge",
        "raw_profit_units": "profit_units",
        "generic_calibrated_profit_units": "profit_units",
        "calibrated_profit_units": "profit_units",
        "goal_environment_adjusted_profit_units": "calibrated_profit_units",
        "goal_environment_adjusted_edge": "calibrated_edge",
    }
    for column, fallback in defaults.items():
        if column not in df.columns and fallback in df.columns:
            df[column] = df[fallback]

    for flag in ["raw_would_bet", "generic_calibrated_would_bet", "calibrated_would_bet"]:
        if flag not in df.columns:
            df[flag] = True
    if "goal_environment_adjusted_would_bet" not in df.columns:
        df["goal_environment_adjusted_would_bet"] = df["calibrated_would_bet"]
    if "adjusted_projected_total_goals" not in df.columns and "projected_total_goals" in df.columns:
        df["adjusted_projected_total_goals"] = df["projected_total_goals"]

    if "actual_total_goals" not in df.columns and "score" in df.columns:
        score_parts = df["score"].astype(str).str.extract(r"^(\d+)-(\d+)$")
        df["actual_total_goals"] = pd.to_numeric(score_parts[0], errors="coerce") + pd.to_numeric(score_parts[1], errors="coerce")

    df["odds_range"] = df["american_odds"].apply(odds_range)
    df["total_price_bucket"] = df["american_odds"].apply(total_price_bucket)
    df["raw_edge_bucket"] = df["raw_edge"].apply(edge_bucket)
    df["calibrated_edge_bucket"] = df["calibrated_edge"].apply(edge_bucket)
    df["projected_goal_total_bucket"] = df.get("projected_total_goals", pd.Series(index=df.index, dtype=float)).apply(projected_goal_bucket)
    df["favorite_strength_bucket"] = df.get("favorite_strength", pd.Series(index=df.index, dtype=float)).apply(favorite_strength_bucket)

    profile = build_team_event_profile(matches)
    if profile.empty:
        df["home_event_bucket"] = "unknown"
        df["away_event_bucket"] = "unknown"
        df["home_team_avg_total_goals"] = pd.NA
        df["away_team_avg_total_goals"] = pd.NA
        df["home_team_over_2_5_rate"] = pd.NA
        df["away_team_over_2_5_rate"] = pd.NA
    else:
        home_profile = profile.add_prefix("home_").rename(columns={"home_team": "home_team"})
        away_profile = profile.add_prefix("away_").rename(columns={"away_team": "away_team"})
        df = df.merge(home_profile, on="home_team", how="left")
        df = df.merge(away_profile, on="away_team", how="left")
        df["home_event_bucket"] = df["home_team_event_bucket"].fillna("unknown")
        df["away_event_bucket"] = df["away_team_event_bucket"].fillna("unknown")

    df["match_event_profile"] = df.apply(lambda r: _match_event_profile(r["home_event_bucket"], r["away_event_bucket"]), axis=1)
    return df


def summarize_totals_by(totals: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    columns = group_cols + TOTALS_SUMMARY_COLUMNS
    if totals.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for key, group in totals.groupby(group_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        raw = group[group["raw_would_bet"] == True]
        generic = group[group["generic_calibrated_would_bet"] == True]
        calibrated = group[group["calibrated_would_bet"] == True]
        adjusted = group[group["goal_environment_adjusted_would_bet"] == True]
        raw_bets = len(raw)
        generic_bets = len(generic)
        calibrated_bets = len(calibrated)
        adjusted_bets = len(adjusted)
        raw_profit = round(float(raw["raw_profit_units"].sum()), 3) if raw_bets else 0.0
        generic_profit = round(float(generic["generic_calibrated_profit_units"].sum()), 3) if generic_bets else 0.0
        calibrated_profit = round(float(calibrated["calibrated_profit_units"].sum()), 3) if calibrated_bets else 0.0
        adjusted_profit = round(float(adjusted["goal_environment_adjusted_profit_units"].sum()), 3) if adjusted_bets else 0.0
        row = dict(zip(group_cols, key, strict=False))
        row.update({
            "candidates": len(group),
            "raw_bets": raw_bets,
            "raw_wins": int(raw["won"].sum()) if raw_bets else 0,
            "raw_profit_units": raw_profit,
            "raw_roi": round(raw_profit / raw_bets, 3) if raw_bets else 0.0,
            "generic_calibrated_bets": generic_bets,
            "generic_calibrated_wins": int(generic["won"].sum()) if generic_bets else 0,
            "generic_calibrated_profit_units": generic_profit,
            "generic_calibrated_roi": round(generic_profit / generic_bets, 3) if generic_bets else 0.0,
            "calibrated_bets": calibrated_bets,
            "calibrated_wins": int(calibrated["won"].sum()) if calibrated_bets else 0,
            "calibrated_profit_units": calibrated_profit,
            "calibrated_roi": round(calibrated_profit / calibrated_bets, 3) if calibrated_bets else 0.0,
            "goal_environment_adjusted_bets": adjusted_bets,
            "goal_environment_adjusted_wins": int(adjusted["won"].sum()) if adjusted_bets else 0,
            "goal_environment_adjusted_profit_units": adjusted_profit,
            "goal_environment_adjusted_roi": round(adjusted_profit / adjusted_bets, 3) if adjusted_bets else 0.0,
            "bets_filtered_out": raw_bets - calibrated_bets,
            "goal_environment_bets_filtered_out": raw_bets - adjusted_bets,
            "avg_american_odds": round(float(group["american_odds"].mean()), 0),
            "avg_raw_edge": round(float(group["raw_edge"].mean()), 4),
            "avg_calibrated_edge": round(float(group["calibrated_edge"].mean()), 4),
            "avg_goal_environment_adjusted_edge": round(float(group["goal_environment_adjusted_edge"].mean()), 4),
            "avg_projected_total_goals": round(float(group["projected_total_goals"].mean()), 3) if "projected_total_goals" in group else pd.NA,
            "avg_adjusted_projected_total_goals": round(float(group["adjusted_projected_total_goals"].mean()), 3) if "adjusted_projected_total_goals" in group else pd.NA,
            "avg_actual_total_goals": round(float(group["actual_total_goals"].mean()), 3) if "actual_total_goals" in group else pd.NA,
            "actual_over_2_5_rate": round(float((group["actual_total_goals"] > 2.5).mean()), 3) if "actual_total_goals" in group else pd.NA,
        })
        rows.append(row)

    return pd.DataFrame(rows, columns=columns).sort_values(["calibrated_profit_units", "raw_profit_units"])


def build_totals_team_breakdown(totals: pd.DataFrame) -> pd.DataFrame:
    columns = ["team", "team_role", "team_event_bucket"] + TOTALS_SUMMARY_COLUMNS
    if totals.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for _, bet in totals.iterrows():
        home = bet.to_dict()
        home["team"] = bet["home_team"]
        home["team_role"] = "home"
        home["team_event_bucket"] = bet.get("home_event_bucket", "unknown")
        rows.append(home)

        away = bet.to_dict()
        away["team"] = bet["away_team"]
        away["team_role"] = "away"
        away["team_event_bucket"] = bet.get("away_event_bucket", "unknown")
        rows.append(away)

    return summarize_totals_by(pd.DataFrame(rows), ["team", "team_role", "team_event_bucket"])


def build_goal_environment_comparison(totals: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "selection",
        "raw_bets",
        "raw_roi",
        "calibrated_bets",
        "calibrated_roi",
        "goal_environment_adjusted_bets",
        "goal_environment_adjusted_roi",
        "goal_environment_bets_filtered_out",
        "goal_environment_adjusted_profit_units",
        "under_improved",
    ]
    if totals.empty:
        return pd.DataFrame(columns=columns)

    summary = summarize_totals_by(totals, ["selection"])
    rows = []
    for _, row in summary.iterrows():
        rows.append({
            "selection": row["selection"],
            "raw_bets": row["raw_bets"],
            "raw_roi": row["raw_roi"],
            "calibrated_bets": row["calibrated_bets"],
            "calibrated_roi": row["calibrated_roi"],
            "goal_environment_adjusted_bets": row["goal_environment_adjusted_bets"],
            "goal_environment_adjusted_roi": row["goal_environment_adjusted_roi"],
            "goal_environment_bets_filtered_out": row["goal_environment_bets_filtered_out"],
            "goal_environment_adjusted_profit_units": row["goal_environment_adjusted_profit_units"],
            "under_improved": bool(
                row["selection"] == "under"
                and row["goal_environment_adjusted_roi"] >= row["raw_roi"]
                and row["goal_environment_adjusted_profit_units"] >= row["raw_profit_units"]
            ),
        })

    total = summarize_totals_by(totals, ["market"]).iloc[0] if "market" in totals.columns else None
    if total is not None:
        rows.append({
            "selection": "all totals",
            "raw_bets": total["raw_bets"],
            "raw_roi": total["raw_roi"],
            "calibrated_bets": total["calibrated_bets"],
            "calibrated_roi": total["calibrated_roi"],
            "goal_environment_adjusted_bets": total["goal_environment_adjusted_bets"],
            "goal_environment_adjusted_roi": total["goal_environment_adjusted_roi"],
            "goal_environment_bets_filtered_out": total["goal_environment_bets_filtered_out"],
            "goal_environment_adjusted_profit_units": total["goal_environment_adjusted_profit_units"],
            "under_improved": pd.NA,
        })
    return pd.DataFrame(rows, columns=columns)


def _worst_line(df: pd.DataFrame, label_col: str, profit_col: str = "raw_profit_units") -> str:
    if df.empty:
        return "No historical total_2_5 rows were available."
    active = df[df["raw_bets"] > 0] if "raw_bets" in df.columns else df
    if active.empty:
        return "No raw totals bets were available."
    row = active.sort_values(profit_col).iloc[0]
    return f"{row[label_col]}: {row[profit_col]} units over {int(row['raw_bets'])} raw bets."


def _better_selection(selection_breakdown: pd.DataFrame) -> str:
    if selection_breakdown.empty:
        return "No over/under comparison is available."
    active = selection_breakdown[selection_breakdown["raw_bets"] > 0].sort_values(["raw_roi", "raw_profit_units"], ascending=False)
    if active.empty:
        return "No raw over/under bets are available."
    best = active.iloc[0]
    worst = active.iloc[-1]
    return (
        f"{best['selection']} was better historically than {worst['selection']} "
        f"on raw totals bets ({best['raw_roi']:.1%} ROI vs {worst['raw_roi']:.1%}). "
        f"After the goal-environment layer, {best['selection']} finished at "
        f"{best['goal_environment_adjusted_roi']:.1%} ROI over {int(best['goal_environment_adjusted_bets'])} bets."
    )


def _comparison_line(comparison: pd.DataFrame) -> str:
    if comparison.empty:
        return "No goal-environment comparison rows available."
    totals = comparison[comparison["selection"] == "all totals"]
    under = comparison[comparison["selection"] == "under"]
    pieces = []
    if not totals.empty:
        row = totals.iloc[0]
        pieces.append(
            f"all totals moved from {row['raw_roi']:.1%} raw ROI to "
            f"{row['goal_environment_adjusted_roi']:.1%} adjusted ROI, with "
            f"{int(row['goal_environment_bets_filtered_out'])} raw totals filtered out"
        )
    if not under.empty:
        row = under.iloc[0]
        improved = "improved" if bool(row["under_improved"]) else "did not improve"
        pieces.append(f"unders {improved} versus raw under results")
    return "; ".join(pieces) + "."


def render_totals_diagnostics_report(
    selection: pd.DataFrame,
    goal_bucket: pd.DataFrame,
    odds_range_report: pd.DataFrame,
    price_bucket: pd.DataFrame,
    raw_edge: pd.DataFrame,
    calibrated_edge: pd.DataFrame,
    team: pd.DataFrame,
    event_profile: pd.DataFrame,
    comparison: pd.DataFrame,
) -> str:
    worst_teams = team[team["raw_bets"] > 0].sort_values("raw_profit_units").head(10) if not team.empty else pd.DataFrame()
    low_goal = goal_bucket[goal_bucket["projected_goal_total_bucket"].astype(str).str.contains("under|2.2", regex=True, na=False)]
    high_goal = goal_bucket[goal_bucket["projected_goal_total_bucket"].astype(str).str.contains("2.8|3.1", regex=True, na=False)]

    lines = [
        "# EPL Betting Lab Totals Diagnostics",
        "",
        "This report uses settled historical total_2_5 backtest rows only. It does not use live odds, does not fabricate prices, and does not place bets.",
        "",
        "Status note: `raw` means the old uncalibrated totals signal. `calibrated` means the current stricter market-specific totals rule used for betting decisions.",
        "",
        "The `goal_environment_adjusted` columns are the current final totals decisions after the extra goal-environment check.",
        "",
        "## Quick answers",
        "",
        f"- Over vs under: {_better_selection(selection)}",
        f"- Worst odds range: {_worst_line(odds_range_report, 'odds_range')}",
        f"- Plus-money vs juiced totals: {_worst_line(price_bucket, 'total_price_bucket')}",
        f"- Worst projected goal bucket: {_worst_line(goal_bucket, 'projected_goal_total_bucket')}",
        f"- Worst raw edge bucket: {_worst_line(raw_edge, 'raw_edge_bucket')}",
        f"- Worst calibrated edge bucket: {_worst_line(calibrated_edge, 'calibrated_edge_bucket')}",
        f"- Goal-environment comparison: {_comparison_line(comparison)}",
        "",
        "## Goal-environment comparison",
        "",
        comparison.to_markdown(index=False) if not comparison.empty else "No goal-environment comparison rows available.",
        "",
        "## Over vs under",
        "",
        selection.to_markdown(index=False) if not selection.empty else "No over/under rows available.",
        "",
        "## Projected goal buckets",
        "",
        goal_bucket.to_markdown(index=False) if not goal_bucket.empty else "No projected goal rows available.",
        "",
        "## Low projected total games",
        "",
        low_goal.to_markdown(index=False) if not low_goal.empty else "No low projected total rows available.",
        "",
        "## High projected total games",
        "",
        high_goal.to_markdown(index=False) if not high_goal.empty else "No high projected total rows available.",
        "",
        "## Odds ranges",
        "",
        odds_range_report.to_markdown(index=False) if not odds_range_report.empty else "No odds range rows available.",
        "",
        "## Raw edge buckets",
        "",
        raw_edge.to_markdown(index=False) if not raw_edge.empty else "No raw edge rows available.",
        "",
        "## Calibrated edge buckets",
        "",
        calibrated_edge.to_markdown(index=False) if not calibrated_edge.empty else "No calibrated edge rows available.",
        "",
        "## Team event profile",
        "",
        event_profile.to_markdown(index=False) if not event_profile.empty else "No high-event or low-event team rows available.",
        "",
        "## Teams most associated with totals losses",
        "",
        worst_teams.to_markdown(index=False) if not worst_teams.empty else "No team rows available.",
        "",
        "## Beginner read",
        "",
        "If raw ROI is negative but calibrated bets are close to zero, the current rule is protecting the bankroll by passing. That is useful, but it also means totals are not truly fixed yet.",
    ]
    return "\n".join(lines)


def save_totals_diagnostics_reports(bets: pd.DataFrame, matches: pd.DataFrame | None, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    totals = enrich_totals_diagnostics(bets, matches)

    reports = {
        "diagnostics": totals,
        "selection": summarize_totals_by(totals, ["selection"]),
        "season": summarize_totals_by(totals, ["season", "selection"]),
        "odds_range": summarize_totals_by(totals, ["odds_range", "total_price_bucket"]),
        "price_bucket": summarize_totals_by(totals, ["total_price_bucket", "selection"]),
        "goal_bucket": summarize_totals_by(totals, ["projected_goal_total_bucket", "selection"]),
        "raw_edge_bucket": summarize_totals_by(totals, ["raw_edge_bucket", "selection"]),
        "calibrated_edge_bucket": summarize_totals_by(totals, ["calibrated_edge_bucket", "selection"]),
        "favorite_strength": summarize_totals_by(totals, ["favorite_strength_bucket", "selection"]),
        "event_profile": summarize_totals_by(totals, ["match_event_profile", "selection"]),
        "team": build_totals_team_breakdown(totals),
        "comparison": build_goal_environment_comparison(totals),
    }

    paths = {
        "diagnostics": output_dir / "backtest_totals_diagnostics.csv",
        "selection": output_dir / "backtest_totals_by_selection.csv",
        "season": output_dir / "backtest_totals_by_season.csv",
        "odds_range": output_dir / "backtest_totals_by_odds_range.csv",
        "price_bucket": output_dir / "backtest_totals_by_price_bucket.csv",
        "goal_bucket": output_dir / "backtest_totals_by_goal_bucket.csv",
        "raw_edge_bucket": output_dir / "backtest_totals_by_raw_edge_bucket.csv",
        "calibrated_edge_bucket": output_dir / "backtest_totals_by_calibrated_edge_bucket.csv",
        "favorite_strength": output_dir / "backtest_totals_by_favorite_strength.csv",
        "event_profile": output_dir / "backtest_totals_by_event_profile.csv",
        "team": output_dir / "backtest_totals_by_team.csv",
        "comparison": output_dir / "backtest_totals_goal_environment_comparison.csv",
    }

    for name, report in reports.items():
        report.to_csv(paths[name], index=False)

    markdown = render_totals_diagnostics_report(
        reports["selection"],
        reports["goal_bucket"],
        reports["odds_range"],
        reports["price_bucket"],
        reports["raw_edge_bucket"],
        reports["calibrated_edge_bucket"],
        reports["team"],
        reports["event_profile"],
        reports["comparison"],
    )
    paths["markdown"] = output_dir / "backtest_totals_diagnostics_report.md"
    paths["markdown"].write_text(markdown, encoding="utf-8")
    return paths
