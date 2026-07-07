from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.models.value import american_to_implied
from epl_betting_lab.reports.backtest_bias import edge_bucket, odds_range


CLV_COLUMNS = [
    "bets",
    "with_closing_odds",
    "missing_closing_odds",
    "positive_clv_bets",
    "positive_clv_rate",
    "avg_open_implied_probability",
    "avg_close_implied_probability",
    "avg_clv_probability_points",
    "avg_clv_american_odds_movement",
    "profit_units",
    "roi",
]


def _closing_odds_column(df: pd.DataFrame) -> str | None:
    for column in ["closing_american_odds", "close_american_odds", "closing_odds"]:
        if column in df.columns:
            return column
    return None


def enrich_clv_bets(bets: pd.DataFrame) -> pd.DataFrame:
    """Add closing-line-value fields without inventing missing closing prices."""
    if bets.empty:
        return bets.copy()

    df = bets.copy()
    final_would_bet_col = "goal_environment_adjusted_would_bet" if "goal_environment_adjusted_would_bet" in df.columns else "calibrated_would_bet"
    if final_would_bet_col in df.columns:
        df = df[df[final_would_bet_col]].copy()
    df = df[df["market"].isin(["1x2", "total_2_5"])].copy()
    if df.empty:
        return df

    if "opening_american_odds" not in df.columns:
        df["opening_american_odds"] = df["american_odds"]
    if "opening_implied_probability" not in df.columns:
        df["opening_implied_probability"] = df["opening_american_odds"].apply(american_to_implied)

    closing_col = _closing_odds_column(df)
    if closing_col is None:
        df["closing_american_odds"] = pd.NA
    else:
        df["closing_american_odds"] = pd.to_numeric(df[closing_col], errors="coerce")

    df["closing_implied_probability"] = df["closing_american_odds"].apply(
        lambda odds: american_to_implied(odds) if pd.notna(odds) else pd.NA
    )
    df["clv_probability_points"] = df["closing_implied_probability"] - df["opening_implied_probability"]
    # Positive means your number got shorter by close, which is usually good.
    df["clv_american_odds_movement"] = df["opening_american_odds"] - df["closing_american_odds"]
    df["has_closing_odds"] = df["closing_american_odds"].notna()
    df["positive_clv"] = df["clv_probability_points"] > 0
    df["odds_range"] = df["opening_american_odds"].apply(odds_range)
    edge_col = "goal_environment_adjusted_edge" if "goal_environment_adjusted_edge" in df.columns else "calibrated_edge"
    if edge_col not in df.columns:
        edge_col = "edge"
    df["edge_bucket"] = df[edge_col].apply(edge_bucket)
    if "goal_environment_adjusted_profit_units" in df.columns:
        df["profit_units"] = df["goal_environment_adjusted_profit_units"]
    elif "calibrated_profit_units" in df.columns:
        df["profit_units"] = df["calibrated_profit_units"]
    return df


def summarize_clv(clv_bets: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    columns = group_cols + CLV_COLUMNS
    if clv_bets.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for key, group in clv_bets.groupby(group_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        with_close = group[group["has_closing_odds"]]
        row = dict(zip(group_cols, key, strict=False))
        bets = len(group)
        close_bets = len(with_close)
        profit = round(float(group["profit_units"].sum()), 3) if "profit_units" in group else 0.0
        row.update({
            "bets": bets,
            "with_closing_odds": close_bets,
            "missing_closing_odds": bets - close_bets,
            "positive_clv_bets": int(with_close["positive_clv"].sum()) if close_bets else 0,
            "positive_clv_rate": round(float(with_close["positive_clv"].mean()), 3) if close_bets else pd.NA,
            "avg_open_implied_probability": round(float(group["opening_implied_probability"].mean()), 4),
            "avg_close_implied_probability": round(float(with_close["closing_implied_probability"].mean()), 4) if close_bets else pd.NA,
            "avg_clv_probability_points": round(float(with_close["clv_probability_points"].mean()), 4) if close_bets else pd.NA,
            "avg_clv_american_odds_movement": round(float(with_close["clv_american_odds_movement"].mean()), 1) if close_bets else pd.NA,
            "profit_units": profit,
            "roi": round(profit / bets, 3) if bets else 0.0,
        })
        rows.append(row)

    return pd.DataFrame(rows, columns=columns).sort_values(["avg_clv_probability_points", "profit_units"], ascending=[False, False])


def build_clv_team_breakdown(clv_bets: pd.DataFrame) -> pd.DataFrame:
    columns = ["team", "team_role"] + CLV_COLUMNS
    if clv_bets.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for _, bet in clv_bets.iterrows():
        home = bet.to_dict()
        home["team"] = bet["home_team"]
        home["team_role"] = "home"
        rows.append(home)

        away = bet.to_dict()
        away["team"] = bet["away_team"]
        away["team_role"] = "away"
        rows.append(away)

    return summarize_clv(pd.DataFrame(rows), ["team", "team_role"])


def render_clv_report(
    market: pd.DataFrame,
    selection: pd.DataFrame,
    team: pd.DataFrame,
    odds_range_report: pd.DataFrame,
    edge: pd.DataFrame,
) -> str:
    total_bets = int(market["bets"].sum()) if not market.empty else 0
    with_close = int(market["with_closing_odds"].sum()) if not market.empty else 0
    if with_close:
        avg_clv = float(market["avg_clv_probability_points"].dropna().mean())
        availability = f"{with_close} of {total_bets} tracked bets have closing odds. Average CLV is {avg_clv:.2%} probability points."
    else:
        availability = (
            f"No tracked bets have closing odds yet. CLV is ready for manual weekly tracking, "
            f"but historical reports will show missing CLV until closing prices are entered."
        )

    lines = [
        "# EPL Betting Lab Closing-Line Value Report",
        "",
        "This report measures whether the model beat the closing market price. It does not use live odds, does not fabricate closing prices, and does not place bets.",
        "",
        "CLV probability points = closing implied probability minus opening implied probability. Positive CLV means the market moved toward your side after the model decision.",
        "",
        "## Quick answers",
        "",
        f"- Closing-odds availability: {availability}",
        "- If closing odds are blank, CLV stays blank instead of being guessed.",
        "- `avg_clv_american_odds_movement` is positive when the price moved shorter in your favor.",
        "",
        "## By market",
        "",
        market.to_markdown(index=False) if not market.empty else "No CLV rows available.",
        "",
        "## By selection",
        "",
        selection.to_markdown(index=False) if not selection.empty else "No CLV rows available.",
        "",
        "## By odds range",
        "",
        odds_range_report.to_markdown(index=False) if not odds_range_report.empty else "No CLV rows available.",
        "",
        "## By edge bucket",
        "",
        edge.to_markdown(index=False) if not edge.empty else "No CLV rows available.",
        "",
        "## By team",
        "",
        team.to_markdown(index=False) if not team.empty else "No CLV rows available.",
    ]
    return "\n".join(lines)


def save_clv_reports(bets: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    clv_bets = enrich_clv_bets(bets)

    reports = {
        "market": summarize_clv(clv_bets, ["market"]),
        "selection": summarize_clv(clv_bets, ["market", "selection"]),
        "team": build_clv_team_breakdown(clv_bets),
        "odds_range": summarize_clv(clv_bets, ["market", "odds_range"]),
        "edge": summarize_clv(clv_bets, ["market", "edge_bucket"]),
    }

    paths = {
        "market": output_dir / "clv_by_market.csv",
        "selection": output_dir / "clv_by_selection.csv",
        "team": output_dir / "clv_by_team.csv",
        "odds_range": output_dir / "clv_by_odds_range.csv",
        "edge": output_dir / "clv_by_edge_bucket.csv",
    }
    for name, report in reports.items():
        report.to_csv(paths[name], index=False)

    paths["markdown"] = output_dir / "clv_report.md"
    paths["markdown"].write_text(
        render_clv_report(
            reports["market"],
            reports["selection"],
            reports["team"],
            reports["odds_range"],
            reports["edge"],
        ),
        encoding="utf-8",
    )
    return paths
