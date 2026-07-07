from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.backtest_bias import edge_bucket, enrich_backtest_bets


CALIBRATION_COLUMNS = [
    "bets",
    "wins",
    "actual_win_rate",
    "avg_model_prob",
    "calibration_gap",
    "avg_book_implied",
    "avg_edge",
    "profit_units",
    "roi",
]


def probability_bucket(model_prob: float) -> str:
    prob = float(model_prob)
    if prob < 0.40:
        return "under 40%"
    if prob < 0.50:
        return "40% to 50%"
    if prob < 0.60:
        return "50% to 60%"
    if prob < 0.70:
        return "60% to 70%"
    return "70% or higher"


def enrich_calibration_bets(bets: pd.DataFrame) -> pd.DataFrame:
    if bets.empty:
        return bets.copy()

    df = enrich_backtest_bets(bets)
    df["probability_bucket"] = df["model_prob"].apply(probability_bucket)
    df["edge_bucket"] = df["edge"].apply(edge_bucket)
    return df


def summarize_calibration(bets: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    df = enrich_calibration_bets(bets)
    if df.empty:
        return pd.DataFrame(columns=group_cols + CALIBRATION_COLUMNS)

    grouped = df.groupby(group_cols, dropna=False).agg(
        bets=("won", "size"),
        wins=("won", "sum"),
        avg_model_prob=("model_prob", "mean"),
        avg_book_implied=("book_implied", "mean"),
        avg_edge=("edge", "mean"),
        profit_units=("profit_units", "sum"),
    ).reset_index()
    grouped["wins"] = grouped["wins"].astype(int)
    grouped["actual_win_rate"] = grouped["wins"] / grouped["bets"]
    grouped["calibration_gap"] = grouped["actual_win_rate"] - grouped["avg_model_prob"]
    grouped["roi"] = grouped["profit_units"] / grouped["bets"]

    grouped["actual_win_rate"] = grouped["actual_win_rate"].round(3)
    grouped["avg_model_prob"] = grouped["avg_model_prob"].round(3)
    grouped["calibration_gap"] = grouped["calibration_gap"].round(3)
    grouped["avg_book_implied"] = grouped["avg_book_implied"].round(3)
    grouped["avg_edge"] = grouped["avg_edge"].round(4)
    grouped["profit_units"] = grouped["profit_units"].round(3)
    grouped["roi"] = grouped["roi"].round(3)
    return grouped[group_cols + CALIBRATION_COLUMNS]


def _worst_gap(df: pd.DataFrame, label_col: str) -> str:
    if df.empty:
        return "No settled bets available."
    row = df.sort_values("calibration_gap").iloc[0]
    gap = row["calibration_gap"]
    direction = "below" if gap < 0 else "above"
    return (
        f"{row[label_col]} won {row['actual_win_rate']:.1%} vs "
        f"{row['avg_model_prob']:.1%} expected, {abs(gap):.1%} {direction} model."
    )


def _shrinkage_note(probability_breakdown: pd.DataFrame, edge_breakdown: pd.DataFrame) -> str:
    if probability_breakdown.empty or edge_breakdown.empty:
        return "Not enough settled bets to judge shrinkage."

    high_prob = probability_breakdown[probability_breakdown["probability_bucket"] == "70% or higher"]
    big_edges = edge_breakdown[edge_breakdown["edge_bucket"].isin(["8% to 12%", "12% or higher"])]
    high_prob_gap = float(high_prob["calibration_gap"].mean()) if not high_prob.empty else 0.0
    big_edge_gap = float(big_edges["calibration_gap"].mean()) if not big_edges.empty else 0.0

    if high_prob_gap < -0.05 or big_edge_gap < -0.05:
        return (
            "Yes. High-confidence or big-edge plays are winning less often than their model probabilities, "
            "so the next model change should test shrinking extreme probabilities toward the market or a "
            "historical baseline before betting them."
        )
    return "Not yet. The current settled-bet sample does not show enough extreme overconfidence to force shrinkage."


def render_calibration_report(
    probability_breakdown: pd.DataFrame,
    market_breakdown: pd.DataFrame,
    side_breakdown: pd.DataFrame,
    edge_breakdown: pd.DataFrame,
) -> str:
    lines = [
        "# EPL Betting Lab Backtest Calibration Report",
        "",
        "This report compares model probabilities to settled historical backtest results. It does not use live odds, fabricate prices, or place bets.",
        "",
        "Status note: the current backtest only logs plays that passed the old `BETTABLE` filter, so this is calibration for fired bets only.",
        "",
        "## Quick answers",
        "",
        f"- Worst probability bucket: {_worst_gap(probability_breakdown, 'probability_bucket')}",
        f"- Worst market: {_worst_gap(market_breakdown, 'market')}",
        f"- Worst side/type: {_worst_gap(side_breakdown, 'selection_context')}",
        f"- Big-edge read: {_worst_gap(edge_breakdown, 'edge_bucket')}",
        f"- Shrink extreme probabilities? {_shrinkage_note(probability_breakdown, edge_breakdown)}",
        "",
        "## Probability buckets",
        "",
        probability_breakdown.to_markdown(index=False) if not probability_breakdown.empty else "No probability rows available.",
        "",
        "## Market calibration",
        "",
        market_breakdown.to_markdown(index=False) if not market_breakdown.empty else "No market rows available.",
        "",
        "## Side and price calibration",
        "",
        side_breakdown.to_markdown(index=False) if not side_breakdown.empty else "No side rows available.",
        "",
        "## Edge calibration",
        "",
        edge_breakdown.to_markdown(index=False) if not edge_breakdown.empty else "No edge rows available.",
    ]
    return "\n".join(lines)


def save_backtest_calibration_reports(bets: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    enriched = enrich_calibration_bets(bets)

    reports = {
        "probability": summarize_calibration(enriched, ["probability_bucket", "status"]),
        "market": summarize_calibration(enriched, ["market", "probability_bucket", "status"]),
        "side": summarize_calibration(enriched, ["selection_context", "favorite_bucket", "odds_range", "status"]),
        "edge": summarize_calibration(enriched, ["edge_bucket", "status"]),
    }

    paths = {
        "probability": output_dir / "backtest_calibration_by_probability.csv",
        "market": output_dir / "backtest_calibration_by_market.csv",
        "side": output_dir / "backtest_calibration_by_side.csv",
        "edge": output_dir / "backtest_calibration_by_edge.csv",
    }

    for name, report in reports.items():
        report.to_csv(paths[name], index=False)

    markdown = render_calibration_report(
        reports["probability"],
        reports["market"],
        reports["side"],
        reports["edge"],
    )
    paths["markdown"] = output_dir / "backtest_calibration_report.md"
    paths["markdown"].write_text(markdown, encoding="utf-8")
    return paths
