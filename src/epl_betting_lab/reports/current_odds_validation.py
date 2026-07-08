from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_matches, load_upcoming_fixtures
from epl_betting_lab.reports.bet_ledger_health import VALID_SELECTIONS
from epl_betting_lab.reports.thursday_best_bets import missing_current_odds_message


VALIDATION_COLUMNS = [
    "severity",
    "issue",
    "row_number",
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "american_odds",
    "book",
    "details",
]
SERIOUS_SEVERITIES = {"error"}


def _is_blank(value: object) -> bool:
    return pd.isna(value) or str(value).strip() == ""


def _clean(value: object) -> str:
    return "" if _is_blank(value) else str(value).strip()


def _clean_key(value: object) -> str:
    return _clean(value).lower()


def _add_issue(
    rows: list[dict[str, object]],
    severity: str,
    issue: str,
    row: pd.Series | None = None,
    row_number: int | None = None,
    details: str = "",
) -> None:
    rows.append({
        "severity": severity,
        "issue": issue,
        "row_number": row_number if row_number is not None else pd.NA,
        "date": row.get("date", pd.NA) if row is not None else pd.NA,
        "home_team": row.get("home_team", pd.NA) if row is not None else pd.NA,
        "away_team": row.get("away_team", pd.NA) if row is not None else pd.NA,
        "market": row.get("market", pd.NA) if row is not None else pd.NA,
        "selection": row.get("selection", pd.NA) if row is not None else pd.NA,
        "american_odds": row.get("american_odds", pd.NA) if row is not None else pd.NA,
        "book": row.get("book", pd.NA) if row is not None else pd.NA,
        "details": details,
    })


def _team_set(matches: pd.DataFrame, fixtures: pd.DataFrame) -> set[str]:
    teams: set[str] = set()
    for frame in [matches, fixtures]:
        for column in ["home_team", "away_team"]:
            if column in frame.columns:
                teams.update(frame[column].dropna().astype(str).str.strip().str.lower())
    return {team for team in teams if team}


def _fixture_keys(fixtures: pd.DataFrame) -> set[tuple[str, str]]:
    if fixtures.empty or not {"home_team", "away_team"}.issubset(fixtures.columns):
        return set()
    return {
        (_clean_key(row["home_team"]), _clean_key(row["away_team"]))
        for _, row in fixtures.iterrows()
        if _clean_key(row.get("home_team")) and _clean_key(row.get("away_team"))
    }


def _duplicate_key_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in ["date", "home_team", "away_team", "market", "selection", "book"] if column in df.columns]


def build_current_odds_validation(
    odds_path: Path | None = None,
    matches: pd.DataFrame | None = None,
    fixtures: pd.DataFrame | None = None,
    max_juice: int = MAX_DEFAULT_JUICE,
) -> pd.DataFrame:
    """Return read-only quality issues for the manual current odds file."""
    path = odds_path or MANUAL_DIR / "current_odds.csv"
    issues: list[dict[str, object]] = []

    if not path.exists():
        _add_issue(issues, "error", "missing_current_odds_csv", details=missing_current_odds_message(path))
        return pd.DataFrame(issues, columns=VALIDATION_COLUMNS)

    odds = pd.read_csv(path, dtype=str)
    if odds.empty:
        _add_issue(issues, "error", "empty_current_odds_csv", details="The odds file exists, but it has no rows to validate.")
        return pd.DataFrame(issues, columns=VALIDATION_COLUMNS)

    for column in ["date", "home_team", "away_team", "market", "selection", "american_odds", "book"]:
        if column not in odds.columns:
            odds[column] = pd.NA

    if matches is None:
        matches = load_matches()
    if fixtures is None:
        fixtures = load_upcoming_fixtures()

    known_teams = _team_set(matches, fixtures)
    fixture_keys = _fixture_keys(fixtures)
    duplicate_columns = _duplicate_key_columns(odds)
    duplicate_mask = odds.duplicated(subset=duplicate_columns, keep=False) if duplicate_columns else pd.Series(False, index=odds.index)

    for index, row in odds.iterrows():
        row_number = int(index) + 2
        home_team = _clean(row.get("home_team"))
        away_team = _clean(row.get("away_team"))
        market = _clean_key(row.get("market"))
        selection = _clean_key(row.get("selection"))
        odds_text = _clean(row.get("american_odds"))

        if duplicate_mask.loc[index]:
            _add_issue(issues, "error", "duplicate_row", row, row_number, "This row appears more than once and could duplicate a recommendation.")
        if not home_team or not away_team:
            _add_issue(issues, "error", "missing_team", row, row_number, "Both home_team and away_team are required.")
        else:
            if known_teams and home_team.lower() not in known_teams:
                _add_issue(issues, "error", "unknown_home_team", row, row_number, "home_team was not found in upcoming fixtures or historical data.")
            if known_teams and away_team.lower() not in known_teams:
                _add_issue(issues, "error", "unknown_away_team", row, row_number, "away_team was not found in upcoming fixtures or historical data.")
            if fixture_keys and (home_team.lower(), away_team.lower()) not in fixture_keys:
                _add_issue(issues, "error", "fixture_not_found", row, row_number, "This home/away pairing does not match an upcoming fixture.")

        if market not in VALID_SELECTIONS:
            _add_issue(issues, "error", "invalid_market", row, row_number, "Supported markets are 1x2, total_2_5, and btts.")
        elif selection not in VALID_SELECTIONS[market]:
            allowed = ", ".join(sorted(VALID_SELECTIONS[market]))
            _add_issue(issues, "error", "invalid_selection", row, row_number, f"Supported selections for {market}: {allowed}.")

        if not odds_text:
            _add_issue(issues, "error", "missing_american_odds", row, row_number, "Enter the real sportsbook American odds for this row.")
        else:
            numeric_odds = pd.to_numeric(odds_text, errors="coerce")
            if pd.isna(numeric_odds):
                _add_issue(issues, "error", "non_numeric_american_odds", row, row_number, "american_odds must be a number like -120 or +145.")
            elif float(numeric_odds) <= max_juice:
                _add_issue(
                    issues,
                    "warning",
                    "heavy_juice",
                    row,
                    row_number,
                    f"Price is worse than the default max-juice rule around {max_juice}. Treat as pass-risk unless clearly justified.",
                )

        if _is_blank(row.get("book")):
            _add_issue(issues, "warning", "missing_book", row, row_number, "Book name is useful for CLV and weekly tracking, but this is not fatal.")
        if market == "total_2_5" and selection == "under":
            _add_issue(
                issues,
                "warning",
                "total_under_caution",
                row,
                row_number,
                "Totals unders have been a historical leak. Use only with extreme caution and current totals protections.",
            )

    return pd.DataFrame(issues, columns=VALIDATION_COLUMNS)


def has_serious_issues(issues: pd.DataFrame) -> bool:
    return not issues.empty and bool(issues["severity"].isin(SERIOUS_SEVERITIES).any())


def render_current_odds_validation_report(issues: pd.DataFrame) -> str:
    if issues.empty:
        quick = "No current odds validation issues found."
        serious = warnings = pd.DataFrame(columns=VALIDATION_COLUMNS)
    else:
        serious = issues[issues["severity"].isin(SERIOUS_SEVERITIES)]
        warnings = issues[~issues["severity"].isin(SERIOUS_SEVERITIES)]
        quick = f"{len(serious)} serious issues and {len(warnings)} warnings found."

    lines = [
        "# Current Odds Validation",
        "",
        "This report checks `data/manual/current_odds.csv`. It does not edit odds, fetch live prices, fabricate prices, or place bets.",
        "",
        "## Quick summary",
        "",
        f"- {quick}",
        "- Serious issues can break matching or make the Thursday report unreliable.",
        "- Warnings are review notes, such as missing book names, heavy juice, or risky totals unders.",
        "",
        "## Serious issues",
        "",
        serious.to_markdown(index=False) if not serious.empty else "No serious issues found.",
        "",
        "## Warnings",
        "",
        warnings.to_markdown(index=False) if not warnings.empty else "No warnings found.",
    ]
    return "\n".join(lines)


def save_current_odds_validation(
    odds_path: Path | None = None,
    output_dir: Path | None = None,
    matches: pd.DataFrame | None = None,
    fixtures: pd.DataFrame | None = None,
) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    issues = build_current_odds_validation(odds_path, matches=matches, fixtures=fixtures)
    csv_path = output_dir / "current_odds_validation.csv"
    markdown_path = output_dir / "current_odds_validation.md"
    issues.to_csv(csv_path, index=False)
    markdown_path.write_text(render_current_odds_validation_report(issues), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}
