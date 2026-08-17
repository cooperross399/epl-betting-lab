from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_upcoming_fixtures
from epl_betting_lab.reports.current_odds_template import build_current_odds_template
from epl_betting_lab.reports.thursday_best_bets import missing_current_odds_message


COMPLETENESS_COLUMNS = [
    "severity",
    "issue",
    "match",
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "book",
    "american_odds",
    "details",
]
SUMMARY_COLUMNS = [
    "total_rows",
    "rows_with_odds_filled",
    "rows_missing_odds",
    "rows_non_numeric_odds",
    "missing_expected_rows",
    "completion_percentage",
    "matches_fully_complete",
    "matches_incomplete",
]
EXPECTED_KEY_COLUMNS = ["date", "home_team", "away_team", "market", "selection"]
DUPLICATE_KEY_COLUMNS = EXPECTED_KEY_COLUMNS + ["book"]


def _is_blank(value: object) -> bool:
    return pd.isna(value) or str(value).strip() == ""


def _clean(value: object) -> str:
    return "" if _is_blank(value) else str(value).strip()


def _clean_key(value: object) -> str:
    return _clean(value).lower()


def _date_key(value: object) -> str:
    if _is_blank(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return _clean_key(value)
    return parsed.strftime("%Y-%m-%d")


def _row_key(row: pd.Series, columns: list[str] = EXPECTED_KEY_COLUMNS) -> tuple[str, ...]:
    values = []
    for column in columns:
        if column == "date":
            values.append(_date_key(row.get(column, "")))
        else:
            values.append(_clean_key(row.get(column, "")))
    return tuple(values)


def _match_text(row: pd.Series) -> str:
    home_team = _clean(row.get("home_team"))
    away_team = _clean(row.get("away_team"))
    if home_team and away_team:
        return f"{home_team} vs {away_team}"
    return ""


def _ensure_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = ""
    return out


def _has_numeric_odds(value: object) -> bool:
    if _is_blank(value):
        return False
    return not pd.isna(pd.to_numeric(_clean(value), errors="coerce"))


def _add_issue(
    rows: list[dict[str, object]],
    severity: str,
    issue: str,
    row: pd.Series | None = None,
    details: str = "",
) -> None:
    rows.append({
        "severity": severity,
        "issue": issue,
        "match": _match_text(row) if row is not None else "",
        "date": row.get("date", "") if row is not None else "",
        "home_team": row.get("home_team", "") if row is not None else "",
        "away_team": row.get("away_team", "") if row is not None else "",
        "market": row.get("market", "") if row is not None else "",
        "selection": row.get("selection", "") if row is not None else "",
        "book": row.get("book", "") if row is not None else "",
        "american_odds": row.get("american_odds", "") if row is not None else "",
        "details": details,
    })


def load_current_odds_for_completeness(path: Path | None = None) -> pd.DataFrame:
    path = path or MANUAL_DIR / "current_odds.csv"
    if not path.exists():
        return pd.DataFrame(columns=[
            "date",
            "home_team",
            "away_team",
            "market",
            "selection",
            "american_odds",
            "book",
        ])
    return pd.read_csv(path, dtype=str).fillna("")


def _expected_rows(
    fixtures: pd.DataFrame | None,
    eligible_markets: Sequence[str] | None = None,
) -> pd.DataFrame:
    if fixtures is None:
        try:
            fixtures = load_upcoming_fixtures()
        except FileNotFoundError:
            fixtures = pd.DataFrame()
    if fixtures.empty:
        return pd.DataFrame(columns=[
            "date",
            "home_team",
            "away_team",
            "market",
            "selection",
            "american_odds",
            "book",
        ])
    expected = build_current_odds_template(fixtures).fillna("")
    if eligible_markets is not None:
        # Market-aware mode: a market the card will not use must not be demanded
        # here. An excluded market is excluded, not an outstanding gap.
        allowed = {str(market).strip().lower() for market in eligible_markets}
        expected = expected[
            expected["market"].astype(str).str.strip().str.lower().isin(allowed)
        ].reset_index(drop=True)
    return expected


def _summary(odds: pd.DataFrame, expected: pd.DataFrame, issues: pd.DataFrame) -> dict[str, object]:
    odds = _ensure_columns(odds, ["american_odds"])
    total_rows = int(len(odds))
    rows_with_odds = int(odds["american_odds"].apply(_has_numeric_odds).sum()) if total_rows else 0
    rows_missing_odds = int(odds["american_odds"].apply(_is_blank).sum()) if total_rows else 0
    rows_non_numeric = int((~odds["american_odds"].apply(_is_blank) & ~odds["american_odds"].apply(_has_numeric_odds)).sum()) if total_rows else 0
    missing_expected = int((issues["issue"] == "missing_expected_market_row").sum()) if not issues.empty else 0
    completion_denominator = total_rows + missing_expected
    completion_percentage = 0.0 if completion_denominator == 0 else rows_with_odds / completion_denominator

    complete_matches, incomplete_matches = _match_completion_counts(odds, expected)
    return {
        "total_rows": total_rows,
        "rows_with_odds_filled": rows_with_odds,
        "rows_missing_odds": rows_missing_odds,
        "rows_non_numeric_odds": rows_non_numeric,
        "missing_expected_rows": missing_expected,
        "completion_percentage": completion_percentage,
        "matches_fully_complete": complete_matches,
        "matches_incomplete": incomplete_matches,
    }


def _match_completion_counts(odds: pd.DataFrame, expected: pd.DataFrame) -> tuple[int, int]:
    if expected.empty:
        odds = _ensure_columns(odds, ["home_team", "away_team", "american_odds"])
        if odds.empty:
            return 0, 0
        grouped = odds.groupby(["home_team", "away_team"], dropna=False)
        complete = int(grouped["american_odds"].apply(lambda values: values.apply(_has_numeric_odds).all()).sum())
        return complete, int(grouped.ngroups - complete)

    odds = _ensure_columns(odds, EXPECTED_KEY_COLUMNS + ["american_odds"])
    numeric_keys = {
        _row_key(row)
        for _, row in odds.iterrows()
        if _has_numeric_odds(row.get("american_odds"))
    }
    complete = 0
    incomplete = 0
    for _, match_rows in expected.groupby(["date", "home_team", "away_team"], dropna=False):
        expected_keys = {_row_key(row) for _, row in match_rows.iterrows()}
        if expected_keys and expected_keys.issubset(numeric_keys):
            complete += 1
        else:
            incomplete += 1
    return complete, incomplete


def build_current_odds_completeness(
    odds_path: Path | None = None,
    fixtures: pd.DataFrame | None = None,
    eligible_markets: Sequence[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return read-only odds entry completeness issues and summary totals.

    `eligible_markets` restricts the check to the markets the card will actually
    use. Rows for other markets are neither demanded nor judged: an excluded
    market must not block a bundle whose eligible markets are complete. Passing
    `None` keeps the historical all-markets behaviour.
    """
    path = odds_path or MANUAL_DIR / "current_odds.csv"
    if not path.exists():
        issues = pd.DataFrame([{
            "severity": "error",
            "issue": "missing_current_odds_csv",
            "match": "",
            "date": "",
            "home_team": "",
            "away_team": "",
            "market": "",
            "selection": "",
            "book": "",
            "american_odds": "",
            "details": missing_current_odds_message(path),
        }], columns=COMPLETENESS_COLUMNS)
        return issues, {column: 0 for column in SUMMARY_COLUMNS}

    odds = load_current_odds_for_completeness(path)
    odds = _ensure_columns(odds, DUPLICATE_KEY_COLUMNS + ["american_odds"])
    expected = _expected_rows(fixtures, eligible_markets)
    if eligible_markets is not None:
        allowed = {str(market).strip().lower() for market in eligible_markets}
        odds = odds[
            odds["market"].astype(str).str.strip().str.lower().isin(allowed)
        ].reset_index(drop=True)
    rows: list[dict[str, object]] = []

    duplicate_mask = odds.duplicated(subset=DUPLICATE_KEY_COLUMNS, keep=False)
    for index, row in odds.iterrows():
        odds_text = row.get("american_odds", "")
        if _is_blank(odds_text):
            _add_issue(rows, "error", "blank_american_odds", row, "Enter the real sportsbook American odds before trusting the Thursday card.")
        elif not _has_numeric_odds(odds_text):
            _add_issue(rows, "error", "non_numeric_american_odds", row, "Use a number like -120 or +145.")

        if _is_blank(row.get("book")):
            _add_issue(rows, "warning", "missing_book", row, "Book name helps CLV and weekly review. Add it when you know the book.")
        if duplicate_mask.loc[index]:
            _add_issue(rows, "error", "duplicate_market_selection_row", row, "This market/selection/book row appears more than once.")

    existing_keys = {_row_key(row) for _, row in odds.iterrows()}
    for _, row in expected.iterrows():
        if _row_key(row) not in existing_keys:
            _add_issue(rows, "error", "missing_expected_market_row", row, "This expected fixture/market/selection row is missing from current_odds.csv.")

    issues = pd.DataFrame(rows, columns=COMPLETENESS_COLUMNS)
    if not issues.empty:
        issues = issues.sort_values(["severity", "date", "home_team", "away_team", "market", "selection"], kind="stable").reset_index(drop=True)
    return issues, _summary(odds, expected, issues)


def render_current_odds_completeness_report(issues: pd.DataFrame, summary: dict[str, object]) -> str:
    completion = float(summary.get("completion_percentage", 0.0))
    serious = issues[issues["severity"] == "error"] if not issues.empty else pd.DataFrame(columns=COMPLETENESS_COLUMNS)
    warnings = issues[issues["severity"] != "error"] if not issues.empty else pd.DataFrame(columns=COMPLETENESS_COLUMNS)
    incomplete_issues = [
        "missing_current_odds_csv",
        "blank_american_odds",
        "non_numeric_american_odds",
        "missing_expected_market_row",
        "duplicate_market_selection_row",
    ]
    incomplete = serious[serious["issue"].isin(incomplete_issues)]
    lines = [
        "# Current Odds Entry Completeness",
        "",
        "This report checks `data/manual/current_odds.csv` before Thursday best bets. It does not edit odds, fetch live prices, fabricate prices, or place bets.",
        "",
        "## Summary",
        "",
        f"- Total rows in current_odds.csv: {int(summary.get('total_rows', 0))}",
        f"- Rows with numeric odds filled: {int(summary.get('rows_with_odds_filled', 0))}",
        f"- Rows missing odds: {int(summary.get('rows_missing_odds', 0))}",
        f"- Rows with non-numeric odds: {int(summary.get('rows_non_numeric_odds', 0))}",
        f"- Missing expected market rows: {int(summary.get('missing_expected_rows', 0))}",
        f"- Completion percentage: {completion:.1%}",
        f"- Matches fully complete: {int(summary.get('matches_fully_complete', 0))}",
        f"- Matches incomplete: {int(summary.get('matches_incomplete', 0))}",
        "",
        "Completion percentage is numeric odds filled divided by existing rows plus any expected fixture/market rows that are missing.",
        "",
        "## Incomplete Matches First",
        "",
        incomplete.to_markdown(index=False) if not incomplete.empty else "No incomplete match/market rows found.",
        "",
        "## Warnings",
        "",
        warnings.to_markdown(index=False) if not warnings.empty else "No warnings found.",
    ]
    return "\n".join(lines)


def save_current_odds_completeness(
    odds_path: Path | None = None,
    output_dir: Path | None = None,
    fixtures: pd.DataFrame | None = None,
) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    issues, summary = build_current_odds_completeness(odds_path, fixtures=fixtures)
    csv_path = output_dir / "current_odds_completeness.csv"
    markdown_path = output_dir / "current_odds_completeness.md"
    issues.to_csv(csv_path, index=False)
    markdown_path.write_text(render_current_odds_completeness_report(issues, summary), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}
