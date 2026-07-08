from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import BANKROLL_UNIT_DOLLARS
from epl_betting_lab.reports.weekly_card import confidence_tier


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
    "fair_american",
    "american_odds",
    "suggested_units",
    "suggested_wager_$",
    "book",
    "qualifies_reason",
    "totals_note",
    "notes",
]


def missing_current_odds_message(path: Path) -> str:
    return (
        f"Missing {path}. Copy data/manual/current_odds_template.csv to "
        f"data/manual/current_odds.csv, then enter real sportsbook odds before "
        f"running the Thursday best-bets report."
    )


def _value(row: pd.Series, column: str, fallback: object = pd.NA) -> object:
    if column not in row or pd.isna(row[column]):
        return fallback
    return row[column]


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
        return f"Calibrated status is {status} with positive calibrated edge and playable price."
    if section == "Leans":
        return "Positive but thinner edge; keep smaller unless the price improves."
    if "too much juice" in status.lower():
        return "Avoid: price is worse than the default max-juice rule around -160."
    if "hot goal environment" in status.lower():
        return "Avoid: totals under protection flagged a hot goal environment."
    if "pre-adjustment edge" in status.lower():
        return "Avoid: totals needed stronger edge before goal-environment adjustment."
    return f"Pass: calibrated status is {status}."


def _section(status: object) -> str:
    status_text = "" if pd.isna(status) else str(status)
    if status_text == "BETTABLE":
        return "Best bets"
    if status_text == "LEAN":
        return "Leans"
    return "Passes / notable avoids"


def build_thursday_best_bets(candidates: pd.DataFrame, max_best_bets: int = 8, max_passes: int = 12) -> pd.DataFrame:
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
    df["qualifies_reason"] = df.apply(lambda row: _qualifies_reason(row, row["section"]), axis=1)
    df["confidence"] = df.apply(lambda row: confidence_tier(float(row["edge"]), float(row["ev_per_unit"])), axis=1)
    df["suggested_units"] = df["confidence"].map({"A": 0.75, "B": 0.5, "C": 0.25, "Lean/Pass": 0.1}).fillna(0.1)
    df.loc[df["section"] == "Passes / notable avoids", "suggested_units"] = 0.0
    df["suggested_wager_$"] = (df["suggested_units"] * BANKROLL_UNIT_DOLLARS).round(2)

    best = df[df["section"] == "Best bets"].sort_values(["edge", "ev_per_unit"], ascending=False).head(max_best_bets)
    leans = df[df["section"] == "Leans"].sort_values(["edge", "ev_per_unit"], ascending=False)
    passes = df[df["section"] == "Passes / notable avoids"].sort_values(["edge", "ev_per_unit"], ascending=False).head(max_passes)
    report = pd.concat([best, leans, passes], ignore_index=True)
    return report[REPORT_COLUMNS]


def render_thursday_best_bets(report: pd.DataFrame) -> str:
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
    ]
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
            if row["totals_note"]:
                lines.append(f"- Totals note: {row['totals_note']}")
            if row["notes"]:
                lines.append(f"- Notes: {row['notes']}")
            lines.append("")
    return "\n".join(lines)


def save_thursday_best_bets(report: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "thursday_best_bets.csv"
    markdown_path = output_dir / "thursday_best_bets.md"
    report.to_csv(csv_path, index=False)
    markdown_path.write_text(render_thursday_best_bets(report), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}
