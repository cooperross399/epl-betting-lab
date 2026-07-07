from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.backtest_bias import edge_bucket, enrich_backtest_bets


CALIBRATION_COLUMNS = [
    "bets",
    "wins",
    "actual_win_rate",
    "avg_raw_model_prob",
    "raw_calibration_gap",
    "avg_calibrated_model_prob",
    "calibrated_calibration_gap",
    "avg_book_implied",
    "avg_raw_edge",
    "avg_calibrated_edge",
    "avg_calibration_weight",
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
    if "calibrated_would_bet" in df.columns:
        df = df[df["calibrated_would_bet"]].copy()
    if "raw_model_prob" not in df.columns:
        df["raw_model_prob"] = df["model_prob"]
    if "calibrated_model_prob" not in df.columns:
        df["calibrated_model_prob"] = df["model_prob"]
    if "raw_edge" not in df.columns:
        df["raw_edge"] = df["edge"]
    if "calibrated_edge" not in df.columns:
        df["calibrated_edge"] = df["edge"]
    if "calibrated_profit_units" not in df.columns:
        df["calibrated_profit_units"] = df["profit_units"]
    if "calibration_weight" not in df.columns:
        df["calibration_weight"] = 0.0

    df["probability_bucket"] = df["calibrated_model_prob"].apply(probability_bucket)
    df["edge_bucket"] = df["calibrated_edge"].apply(edge_bucket)
    df["profit_units"] = df["calibrated_profit_units"]
    df["model_prob"] = df["calibrated_model_prob"]
    df["edge"] = df["calibrated_edge"]
    return df


def summarize_calibration(bets: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    df = enrich_calibration_bets(bets)
    if df.empty:
        return pd.DataFrame(columns=group_cols + CALIBRATION_COLUMNS)

    grouped = df.groupby(group_cols, dropna=False).agg(
        bets=("won", "size"),
        wins=("won", "sum"),
        avg_raw_model_prob=("raw_model_prob", "mean"),
        avg_calibrated_model_prob=("calibrated_model_prob", "mean"),
        avg_book_implied=("book_implied", "mean"),
        avg_raw_edge=("raw_edge", "mean"),
        avg_calibrated_edge=("calibrated_edge", "mean"),
        avg_calibration_weight=("calibration_weight", "mean"),
        profit_units=("profit_units", "sum"),
    ).reset_index()
    grouped["wins"] = grouped["wins"].astype(int)
    grouped["actual_win_rate"] = grouped["wins"] / grouped["bets"]
    grouped["raw_calibration_gap"] = grouped["actual_win_rate"] - grouped["avg_raw_model_prob"]
    grouped["calibrated_calibration_gap"] = grouped["actual_win_rate"] - grouped["avg_calibrated_model_prob"]
    grouped["roi"] = grouped["profit_units"] / grouped["bets"]

    grouped["actual_win_rate"] = grouped["actual_win_rate"].round(3)
    grouped["avg_raw_model_prob"] = grouped["avg_raw_model_prob"].round(3)
    grouped["raw_calibration_gap"] = grouped["raw_calibration_gap"].round(3)
    grouped["avg_calibrated_model_prob"] = grouped["avg_calibrated_model_prob"].round(3)
    grouped["calibrated_calibration_gap"] = grouped["calibrated_calibration_gap"].round(3)
    grouped["avg_book_implied"] = grouped["avg_book_implied"].round(3)
    grouped["avg_raw_edge"] = grouped["avg_raw_edge"].round(4)
    grouped["avg_calibrated_edge"] = grouped["avg_calibrated_edge"].round(4)
    grouped["avg_calibration_weight"] = grouped["avg_calibration_weight"].round(3)
    grouped["profit_units"] = grouped["profit_units"].round(3)
    grouped["roi"] = grouped["roi"].round(3)
    return grouped[group_cols + CALIBRATION_COLUMNS]


def _worst_gap(df: pd.DataFrame, label_col: str) -> str:
    if df.empty:
        return "No settled bets available."
    row = df.sort_values("calibrated_calibration_gap").iloc[0]
    gap = row["calibrated_calibration_gap"]
    direction = "below" if gap < 0 else "above"
    return (
        f"{row[label_col]} won {row['actual_win_rate']:.1%} vs "
        f"{row['avg_calibrated_model_prob']:.1%} calibrated expected, {abs(gap):.1%} {direction} model."
    )


def _shrinkage_note(probability_breakdown: pd.DataFrame, edge_breakdown: pd.DataFrame) -> str:
    if probability_breakdown.empty or edge_breakdown.empty:
        return "Not enough settled bets to judge shrinkage."

    high_prob = probability_breakdown[probability_breakdown["probability_bucket"] == "70% or higher"]
    big_edges = edge_breakdown[edge_breakdown["edge_bucket"].isin(["8% to 12%", "12% or higher"])]
    high_prob_gap = float(high_prob["calibrated_calibration_gap"].mean()) if not high_prob.empty else 0.0
    big_edge_gap = float(big_edges["calibrated_calibration_gap"].mean()) if not big_edges.empty else 0.0

    if high_prob_gap < -0.05 or big_edge_gap < -0.05:
        return (
            "Still yes. High-confidence or big-edge plays remain below calibrated probabilities, "
            "so future tuning should keep shrinking or filter those spots more aggressively."
        )
    return "The first shrinkage pass helped enough that extreme overconfidence is less severe in this settled-bet sample."


def render_calibration_report(
    probability_breakdown: pd.DataFrame,
    market_breakdown: pd.DataFrame,
    side_breakdown: pd.DataFrame,
    edge_breakdown: pd.DataFrame,
) -> str:
    lines = [
        "# EPL Betting Lab Backtest Calibration Report",
        "",
        "This report compares raw and calibrated model probabilities to settled historical backtest results. It does not use live odds, fabricate prices, or place bets.",
        "",
        "Status note: these rows are calibrated betting decisions. Raw probability columns are included for before/after comparison.",
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


def render_market_specific_comparison(summary: pd.DataFrame) -> str:
    if summary.empty:
        return "# EPL Betting Lab Market-Specific Calibration Comparison\n\nNo backtest summary available."

    display_cols = [
        "market",
        "raw_bets",
        "raw_roi",
        "generic_calibrated_bets",
        "generic_calibrated_roi",
        "calibrated_bets",
        "calibrated_roi",
        "bets_filtered_out",
        "calibrated_profit_units",
    ]
    available = [col for col in display_cols if col in summary.columns]
    table = summary[available].copy()

    lines = [
        "# EPL Betting Lab Market-Specific Calibration Comparison",
        "",
        "This compares the old raw model, the generic shrinkage layer, and the new market-specific calibration settings.",
        "",
        "- `generic_calibrated` means the same shrinkage rules for every market.",
        "- `calibrated` means market-specific rules, including stricter total_2_5 thresholds.",
        "- This report uses historical backtest odds only. It does not use live odds, fabricate prices, or place bets.",
        "",
        table.to_markdown(index=False),
    ]
    return "\n".join(lines)


def save_market_specific_comparison(summary: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "csv": output_dir / "backtest_market_specific_calibration_comparison.csv",
        "markdown": output_dir / "backtest_market_specific_calibration_comparison.md",
    }
    summary.to_csv(paths["csv"], index=False)
    paths["markdown"].write_text(render_market_specific_comparison(summary), encoding="utf-8")
    return paths
