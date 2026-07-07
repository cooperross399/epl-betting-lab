from __future__ import annotations

from pathlib import Path

import pandas as pd


SUMMARY_COLUMNS = [
    "bets",
    "wins",
    "losses",
    "win_rate",
    "profit_units",
    "roi",
    "avg_american_odds",
    "avg_raw_edge",
    "avg_calibrated_edge",
]


def odds_range(american_odds: float) -> str:
    odds = float(american_odds)
    if odds < -160:
        return "worse than -160"
    if odds < -120:
        return "-160 to -121"
    if odds <= 100:
        return "-120 to +100"
    if odds <= 200:
        return "+101 to +200"
    if odds <= 400:
        return "+201 to +400"
    return "+401 or longer"


def edge_bucket(edge: float) -> str:
    edge = float(edge)
    if edge < 0.035:
        return "under 3.5%"
    if edge < 0.05:
        return "3.5% to 5%"
    if edge < 0.08:
        return "5% to 8%"
    if edge < 0.12:
        return "8% to 12%"
    return "12% or higher"


def favorite_bucket(american_odds: float) -> str:
    odds = float(american_odds)
    if odds < 0:
        return "favorite / juiced"
    if odds == 100:
        return "even money"
    return "underdog / plus money"


def selection_context(market: str, selection: str) -> str:
    if market == "1x2":
        if selection == "home":
            return "home side"
        if selection == "away":
            return "away side"
        if selection == "draw":
            return "draw"
    if market == "total_2_5":
        return f"total {selection}"
    return selection


def enrich_backtest_bets(bets: pd.DataFrame) -> pd.DataFrame:
    """Add beginner-friendly diagnostic columns to settled backtest bets."""
    if bets.empty:
        return bets.copy()

    df = bets.copy()
    if "status" not in df.columns:
        df["status"] = "BETTABLE"
    if "calibrated_would_bet" in df.columns:
        df = df[df["calibrated_would_bet"]].copy()
    if "raw_edge" not in df.columns:
        df["raw_edge"] = df["edge"]
    if "calibrated_edge" not in df.columns:
        df["calibrated_edge"] = df["edge"]
    if "calibrated_profit_units" not in df.columns:
        df["calibrated_profit_units"] = df["profit_units"]

    df["odds_range"] = df["american_odds"].apply(odds_range)
    df["edge_bucket"] = df["calibrated_edge"].apply(edge_bucket)
    df["favorite_bucket"] = df["american_odds"].apply(favorite_bucket)
    df["selection_context"] = df.apply(lambda r: selection_context(r["market"], r["selection"]), axis=1)
    df["profit_units"] = df["calibrated_profit_units"]
    df["edge"] = df["calibrated_edge"]
    return df


def summarize_by(bets: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    df = enrich_backtest_bets(bets)
    if df.empty:
        return pd.DataFrame(columns=group_cols + SUMMARY_COLUMNS)

    grouped = df.groupby(group_cols, dropna=False).agg(
        bets=("won", "size"),
        wins=("won", "sum"),
        profit_units=("profit_units", "sum"),
        avg_american_odds=("american_odds", "mean"),
        avg_raw_edge=("raw_edge", "mean"),
        avg_calibrated_edge=("calibrated_edge", "mean"),
    ).reset_index()
    grouped["wins"] = grouped["wins"].astype(int)
    grouped["losses"] = grouped["bets"] - grouped["wins"]
    grouped["win_rate"] = (grouped["wins"] / grouped["bets"]).round(3)
    grouped["profit_units"] = grouped["profit_units"].round(3)
    grouped["roi"] = (grouped["profit_units"] / grouped["bets"]).round(3)
    grouped["avg_american_odds"] = grouped["avg_american_odds"].round(0)
    grouped["avg_raw_edge"] = grouped["avg_raw_edge"].round(4)
    grouped["avg_calibrated_edge"] = grouped["avg_calibrated_edge"].round(4)
    return grouped[group_cols + SUMMARY_COLUMNS].sort_values("profit_units")


def build_team_breakdown(bets: pd.DataFrame) -> pd.DataFrame:
    df = enrich_backtest_bets(bets)
    if df.empty:
        return pd.DataFrame(columns=["team", "team_role", "bet_on_team"] + SUMMARY_COLUMNS)

    rows: list[dict[str, object]] = []
    for _, bet in df.iterrows():
        for role, team in [("home", bet["home_team"]), ("away", bet["away_team"])]:
            bet_on_team = (bet["market"] == "1x2" and bet["selection"] == role)
            row = bet.to_dict()
            row["team"] = team
            row["team_role"] = role
            row["bet_on_team"] = bool(bet_on_team)
            rows.append(row)

    team_rows = pd.DataFrame(rows)
    return summarize_by(team_rows, ["team", "team_role", "bet_on_team"])


def build_threshold_breakdown(bets: pd.DataFrame) -> pd.DataFrame:
    df = enrich_backtest_bets(bets)
    columns = ["min_edge_threshold", "bets", "wins", "losses", "win_rate", "profit_units", "roi"]
    if df.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for threshold in [0.035, 0.05, 0.08, 0.10, 0.12, 0.15]:
        subset = df[df["edge"] >= threshold]
        if subset.empty:
            rows.append({
                "min_edge_threshold": threshold,
                "bets": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "profit_units": 0.0,
                "roi": 0.0,
            })
            continue
        wins = int(subset["won"].sum())
        bets_count = int(len(subset))
        profit = round(float(subset["profit_units"].sum()), 3)
        rows.append({
            "min_edge_threshold": threshold,
            "bets": bets_count,
            "wins": wins,
            "losses": bets_count - wins,
            "win_rate": round(wins / bets_count, 3),
            "profit_units": profit,
            "roi": round(profit / bets_count, 3),
        })
    return pd.DataFrame(rows, columns=columns)


def render_bias_report(
    market_breakdown: pd.DataFrame,
    odds_breakdown: pd.DataFrame,
    team_breakdown: pd.DataFrame,
    edge_breakdown: pd.DataFrame,
    favorite_breakdown: pd.DataFrame,
    threshold_breakdown: pd.DataFrame,
) -> str:
    def top_loss(df: pd.DataFrame, label_col: str) -> str:
        if df.empty:
            return "No settled bets available."
        row = df.sort_values("profit_units").iloc[0]
        return f"{row[label_col]} lost {row['profit_units']} units across {int(row['bets'])} bets."

    live_thresholds = threshold_breakdown[threshold_breakdown["bets"] > 0]
    best_threshold = live_thresholds.sort_values(["roi", "profit_units"], ascending=False).head(1)
    threshold_line = "No threshold result available."
    if not best_threshold.empty:
        row = best_threshold.iloc[0]
        threshold_line = (
            f"A stricter edge cutoff of {row['min_edge_threshold']:.1%} had the best ROI "
            f"among already-bettable historical plays: {row['roi']:.1%} over {int(row['bets'])} bets."
        )

    losing_teams = team_breakdown.sort_values("profit_units").head(10) if not team_breakdown.empty else pd.DataFrame()

    lines = [
        "# EPL Betting Lab Backtest Bias Report",
        "",
        "This report uses settled historical backtest bets only. It does not use live odds, does not fabricate prices, and does not place bets.",
        "",
        "Status note: these rows use calibrated `BETTABLE` decisions. Raw edge columns are included for before/after comparison.",
        "",
        "## Quick answers",
        "",
        f"- Worst market: {top_loss(market_breakdown, 'market')}",
        f"- Worst odds range: {top_loss(odds_breakdown, 'odds_range')}",
        f"- Favorite vs underdog read: {top_loss(favorite_breakdown, 'favorite_bucket')}",
        f"- Small-edge read: {top_loss(edge_breakdown, 'edge_bucket')}",
        f"- Threshold check: {threshold_line}",
        "",
        "## Favorite vs underdog",
        "",
        favorite_breakdown.to_markdown(index=False) if not favorite_breakdown.empty else "No favorite/underdog rows available.",
        "",
        "## Edge buckets",
        "",
        edge_breakdown.to_markdown(index=False) if not edge_breakdown.empty else "No edge bucket rows available.",
        "",
        "## Teams most associated with losses",
        "",
        losing_teams.to_markdown(index=False) if not losing_teams.empty else "No team rows available.",
        "",
        "## Threshold check",
        "",
        "This section tests stricter cutoffs on calibrated bets that fired. It does not prove the model would have found every possible pass or lean.",
        "",
        threshold_breakdown.to_markdown(index=False) if not threshold_breakdown.empty else "No threshold rows available.",
    ]
    return "\n".join(lines)


def save_backtest_bias_reports(bets: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    enriched = enrich_backtest_bets(bets)

    reports = {
        "market": summarize_by(enriched, ["market", "status"]),
        "season": summarize_by(enriched, ["season", "market", "status"]),
        "odds_range": summarize_by(enriched, ["odds_range", "favorite_bucket", "status"]),
        "team": build_team_breakdown(enriched),
        "edge_bucket": summarize_by(enriched, ["edge_bucket", "status"]),
        "home_away": summarize_by(enriched, ["selection_context", "status"]),
        "favorite": summarize_by(enriched, ["favorite_bucket", "status"]),
        "threshold": build_threshold_breakdown(enriched),
    }

    paths = {
        "market": output_dir / "backtest_market_breakdown.csv",
        "season": output_dir / "backtest_season_breakdown.csv",
        "odds_range": output_dir / "backtest_odds_range_breakdown.csv",
        "team": output_dir / "backtest_team_breakdown.csv",
        "edge_bucket": output_dir / "backtest_edge_bucket_breakdown.csv",
        "home_away": output_dir / "backtest_home_away_breakdown.csv",
        "favorite": output_dir / "backtest_favorite_underdog_breakdown.csv",
        "threshold": output_dir / "backtest_threshold_breakdown.csv",
    }

    for name, report in reports.items():
        report.to_csv(paths[name], index=False)

    markdown = render_bias_report(
        reports["market"],
        reports["odds_range"],
        reports["team"],
        reports["edge_bucket"],
        reports["favorite"],
        reports["threshold"],
    )
    paths["markdown"] = output_dir / "backtest_bias_report.md"
    paths["markdown"].write_text(markdown, encoding="utf-8")
    return paths
