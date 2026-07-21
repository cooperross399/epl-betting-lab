from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.workflow_status import inspect_current_odds_date_freshness


REPORT_COLUMNS = [
    "row_number",
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "american_odds",
    "book",
    "freshness_status",
    "recommended_action",
]


def _empty_report() -> pd.DataFrame:
    return pd.DataFrame(columns=REPORT_COLUMNS)


def _summary(
    *,
    status: str,
    message: str,
    today: date,
    next_step: str,
    total_rows: int = 0,
    stale_rows: int = 0,
    current_rows: int = 0,
    invalid_date_rows: int = 0,
    blank_date_rows: int = 0,
    earliest_odds_date: str = "",
    latest_odds_date: str = "",
    home_freshness_status: str = "Not checked",
) -> dict[str, object]:
    return {
        "status": status,
        "message": message,
        "checked_date": today.isoformat(),
        "total_rows": total_rows,
        "stale_rows": stale_rows,
        "current_rows": current_rows,
        "invalid_date_rows": invalid_date_rows,
        "blank_date_rows": blank_date_rows,
        "earliest_odds_date": earliest_odds_date,
        "latest_odds_date": latest_odds_date,
        "home_freshness_status": home_freshness_status,
        "next_step": next_step,
    }


def _column(odds: pd.DataFrame, name: str) -> pd.Series:
    if name in odds.columns:
        return odds[name].fillna("").astype(str)
    return pd.Series("", index=odds.index, dtype=str)


def _next_step(stale_rows: int, current_rows: int, date_issues: int) -> str:
    if date_issues:
        prefix = f"Fix the {date_issues} blank or invalid date row(s) before Thursday analysis."
        if stale_rows:
            return f"{prefix} Then review the stale rows and remove or archive them manually."
        return prefix
    if stale_rows and current_rows:
        return (
            "Keep the today/future rows. Review the stale rows and remove or archive them manually "
            "before the next Thursday analysis."
        )
    if stale_rows:
        return (
            "Current odds are tied to past matches. Remove or archive the stale rows manually, "
            "then import or update odds before Thursday analysis."
        )
    return "No stale rows were found. Keep the today/future odds and continue with current-odds validation."


def build_stale_current_odds_report(
    odds_path: Path | None = None,
    *,
    today: date | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Classify current-odds rows without changing the source file."""
    path = odds_path or MANUAL_DIR / "current_odds.csv"
    local_today = today or date.today()

    if not path.exists():
        return _empty_report(), _summary(
            status="Missing file",
            message=f"Current odds file not found: {path}",
            today=local_today,
            next_step=(
                "Create it with `python scripts/create_current_odds_template.py`, fill in real sportsbook "
                "prices, then run this report again."
            ),
        )

    try:
        odds = pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return _empty_report(), _summary(
            status="Empty file",
            message="The current odds file is empty.",
            today=local_today,
            next_step="Create or import current odds before running Thursday analysis.",
        )
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        return _empty_report(), _summary(
            status="Unreadable file",
            message=f"The current odds file could not be read: {exc}",
            today=local_today,
            next_step="Fix the CSV file, then run this read-only report again.",
        )

    if odds.empty:
        return _empty_report(), _summary(
            status="Empty file",
            message="The current odds file has column headers but no rows.",
            today=local_today,
            next_step="Create or import current odds before running Thursday analysis.",
        )
    if "date" not in odds.columns:
        return _empty_report(), _summary(
            status="Missing date column",
            message="The current odds file is missing the `date` column.",
            today=local_today,
            next_step="Add valid match dates to current odds, then run this report again.",
            total_rows=len(odds),
        )

    date_text = _column(odds, "date").str.strip()
    blank_mask = date_text.eq("")
    parsed = pd.to_datetime(date_text.mask(blank_mask), errors="coerce")
    invalid_mask = ~blank_mask & parsed.isna()
    valid_mask = parsed.notna()
    stale_mask = valid_mask & parsed.map(lambda value: value.date() < local_today if pd.notna(value) else False)
    current_mask = valid_mask & ~stale_mask

    status = pd.Series("Current", index=odds.index, dtype=str)
    action = pd.Series("Keep", index=odds.index, dtype=str)
    status.loc[stale_mask] = "Stale"
    action.loc[stale_mask] = "Remove/archive"
    status.loc[invalid_mask] = "Invalid date"
    action.loc[invalid_mask] = "Fix date"
    status.loc[blank_mask] = "Blank date"
    action.loc[blank_mask] = "Fix date"

    report = pd.DataFrame(
        {
            "row_number": range(2, len(odds) + 2),
            "date": _column(odds, "date"),
            "home_team": _column(odds, "home_team"),
            "away_team": _column(odds, "away_team"),
            "market": _column(odds, "market"),
            "selection": _column(odds, "selection"),
            "american_odds": _column(odds, "american_odds"),
            "book": _column(odds, "book"),
            "freshness_status": status,
            "recommended_action": action,
        },
        columns=REPORT_COLUMNS,
    )

    valid_dates = parsed.loc[valid_mask].map(lambda value: value.date())
    stale_rows = int(stale_mask.sum())
    current_rows = int(current_mask.sum())
    invalid_rows = int(invalid_mask.sum())
    blank_rows = int(blank_mask.sum())
    freshness = inspect_current_odds_date_freshness(path, today=local_today)
    summary = _summary(
        status="Checked",
        message="Every current-odds row was classified using its match date.",
        today=local_today,
        next_step=_next_step(stale_rows, current_rows, invalid_rows + blank_rows),
        total_rows=len(report),
        stale_rows=stale_rows,
        current_rows=current_rows,
        invalid_date_rows=invalid_rows,
        blank_date_rows=blank_rows,
        earliest_odds_date=min(valid_dates).isoformat() if not valid_dates.empty else "",
        latest_odds_date=max(valid_dates).isoformat() if not valid_dates.empty else "",
        home_freshness_status=freshness.status,
    )
    return report, summary


def render_stale_current_odds_report(
    report: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    """Render the row-level report as beginner-friendly markdown."""
    stale = report[report["freshness_status"] == "Stale"] if not report.empty else report
    date_issues = (
        report[report["freshness_status"].isin(["Invalid date", "Blank date"])]
        if not report.empty
        else report
    )
    current = report[report["freshness_status"] == "Current"] if not report.empty else report
    lines = [
        "# Stale Current Odds Report",
        "",
        "This report reads `data/manual/current_odds.csv` and never edits it. It does not fetch or guess odds, place bets, or change model logic.",
        "",
        "## Summary",
        "",
        f"- Report status: {summary.get('status', 'Not checked')}",
        f"- Home freshness status: {summary.get('home_freshness_status', 'Not checked')}",
        f"- Date checked against: {summary.get('checked_date', '')}",
        f"- Total rows: {int(summary.get('total_rows', 0))}",
        f"- Stale rows: {int(summary.get('stale_rows', 0))}",
        f"- Current rows: {int(summary.get('current_rows', 0))}",
        f"- Invalid-date rows: {int(summary.get('invalid_date_rows', 0))}",
        f"- Blank-date rows: {int(summary.get('blank_date_rows', 0))}",
        f"- Earliest valid odds date: {summary.get('earliest_odds_date') or 'Not available'}",
        f"- Latest valid odds date: {summary.get('latest_odds_date') or 'Not available'}",
        "",
        str(summary.get("message", "")),
        "",
        "## Next Step",
        "",
        str(summary.get("next_step", "Run the report again after current odds are available.")),
        "",
    ]
    if report.empty:
        lines.extend(
            [
                "## Row Details",
                "",
                "No current-odds rows were available to classify.",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Stale Rows",
            "",
            stale.to_markdown(index=False) if not stale.empty else "No stale rows found.",
            "",
            "## Dates To Fix",
            "",
            date_issues.to_markdown(index=False) if not date_issues.empty else "No blank or invalid dates found.",
            "",
            "## Current Rows",
            "",
            current.to_markdown(index=False) if not current.empty else "No today/future rows found.",
        ]
    )
    return "\n".join(lines)


def save_stale_current_odds_report(
    odds_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    today: date | None = None,
) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    report, summary = build_stale_current_odds_report(odds_path, today=today)
    csv_path = output_dir / "stale_current_odds_report.csv"
    markdown_path = output_dir / "stale_current_odds_report.md"
    report.to_csv(csv_path, index=False)
    markdown_path.write_text(render_stale_current_odds_report(report, summary), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}
