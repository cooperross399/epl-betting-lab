from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR, PROCESSED_DIR
from epl_betting_lab.providers.base import atomic_write_report


SLATE_CHECK_JSON_FILENAME = "fixture_slate_check.json"
SLATE_CHECK_MARKDOWN_FILENAME = "fixture_slate_check.md"
SLATE_CHECK_CSV_FILENAME = "fixture_slate_check.csv"

SLATE_STATUSES = (
    "Slate ready for manual confirmation",
    "Slate ready with warnings",
    "Needs slate fixes",
    "Missing fixtures",
)
ISSUE_COLUMNS = [
    "severity",
    "category",
    "date",
    "home_team",
    "away_team",
    "detail",
    "suggested_action",
]
MATCHWEEK_COLUMNS = [
    "matchweek_group",
    "first_date",
    "last_date",
    "fixture_count",
    "unique_teams",
    "double_booked_teams",
    "note",
]
REQUIRED_COLUMNS = ("date", "home_team", "away_team")
FULL_MATCHWEEK_FIXTURES = 10
# Fixture dates more than this many days apart are treated as separate
# matchweek groups when checking for double-booked teams.
MATCHWEEK_GAP_DAYS = 3

CONFIRMATION_CHECKLIST = (
    "Compare every fixture and date against the official EPL schedule for the "
    "same matchweek before entering odds.",
    "Check for postponed, rescheduled, or TV-moved kickoffs since this file was "
    "last edited.",
    "Confirm team spellings match Football-Data naming (for example `Man United`, "
    "`Man City`, `Nott'm Forest`, `Tottenham`, `Newcastle`).",
    "If the slate changed, update `data/manual/upcoming_fixtures.csv` first, then "
    "rerun `python scripts/run_week1_launch_readiness.py` so the odds template "
    "matches the corrected slate.",
)


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _issue(
    severity: str,
    category: str,
    detail: str,
    suggested_action: str,
    *,
    fixture_date: str = "",
    home_team: str = "",
    away_team: str = "",
) -> dict[str, str]:
    return {
        "severity": severity,
        "category": category,
        "date": fixture_date,
        "home_team": home_team,
        "away_team": away_team,
        "detail": detail,
        "suggested_action": suggested_action,
    }


def _load_historical_teams(matches_path: Path) -> tuple[set[str], str]:
    if not matches_path.exists():
        return set(), (
            f"Historical matches were not found at {matches_path}; team-name "
            "spelling could not be cross-checked."
        )
    try:
        matches = pd.read_csv(matches_path, usecols=["home_team", "away_team"])
    except (OSError, UnicodeError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        return set(), f"Historical matches at {matches_path} could not be read: {exc}"
    teams = {
        _clean(team)
        for column in ("home_team", "away_team")
        for team in matches[column].tolist()
    }
    teams.discard("")
    return teams, f"Team names were cross-checked against {len(teams)} historical team name(s)."


def _load_odds_fixture_keys(
    current_odds_path: Path,
) -> tuple[set[tuple[str, str, str]] | None, str]:
    if not current_odds_path.exists():
        return None, (
            f"No odds file exists yet at {current_odds_path}; the slate/odds "
            "cross-check was skipped."
        )
    try:
        odds = pd.read_csv(current_odds_path, dtype=str)
    except (OSError, UnicodeError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        return None, f"The odds file at {current_odds_path} could not be read: {exc}"
    if not {"date", "home_team", "away_team"}.issubset(odds.columns):
        return None, (
            f"The odds file at {current_odds_path} is missing fixture columns; "
            "the slate/odds cross-check was skipped."
        )
    keys = {
        (_clean(row["date"]), _clean(row["home_team"]), _clean(row["away_team"]))
        for _, row in odds.iterrows()
    }
    keys.discard(("", "", ""))
    return keys, "The existing odds file was cross-checked against the slate (read-only)."


def _assign_matchweek_groups(valid_dates: list[date]) -> dict[date, int]:
    groups: dict[date, int] = {}
    group = 0
    previous: date | None = None
    for value in sorted(set(valid_dates)):
        if previous is not None and (value - previous).days > MATCHWEEK_GAP_DAYS:
            group += 1
        groups[value] = group
        previous = value
    return groups


def build_fixture_slate_check(
    fixtures_path: Path | None = None,
    *,
    matches_path: Path | None = None,
    current_odds_path: Path | None = None,
    today: date | None = None,
) -> dict[str, object]:
    """Build the read-only fixture slate confirmation report. Nothing is edited."""
    fixtures_path = fixtures_path or MANUAL_DIR / "upcoming_fixtures.csv"
    matches_path = matches_path or PROCESSED_DIR / "epl_historical_matches.csv"
    current_odds_path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    today = today or date.today()

    issues: list[dict[str, str]] = []
    matchweeks = pd.DataFrame(columns=MATCHWEEK_COLUMNS)
    notes: list[str] = []
    fixture_count = 0

    if not fixtures_path.exists():
        issues.append(
            _issue(
                "error",
                "Missing file",
                f"No fixture slate exists at {fixtures_path}.",
                "Create data/manual/upcoming_fixtures.csv with the current Week 1 "
                "fixtures before entering odds.",
            )
        )
        return _finish(
            "Missing fixtures", issues, matchweeks, notes, fixtures_path, fixture_count, today
        )

    try:
        fixtures = pd.read_csv(fixtures_path, dtype=str)
    except (OSError, UnicodeError, ValueError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        issues.append(
            _issue(
                "error",
                "Unreadable file",
                f"The fixture slate could not be read: {exc}",
                "Fix or recreate data/manual/upcoming_fixtures.csv as a plain CSV.",
            )
        )
        return _finish(
            "Needs slate fixes", issues, matchweeks, notes, fixtures_path, fixture_count, today
        )

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in fixtures.columns]
    if missing_columns:
        issues.append(
            _issue(
                "error",
                "Missing columns",
                "The fixture slate is missing required column(s): "
                + ", ".join(missing_columns),
                "Add the missing column header(s); the slate needs date, home_team, "
                "and away_team.",
            )
        )
        return _finish(
            "Needs slate fixes", issues, matchweeks, notes, fixtures_path, fixture_count, today
        )

    fixture_count = int(len(fixtures))
    if fixture_count == 0:
        issues.append(
            _issue(
                "error",
                "Empty slate",
                "The fixture slate has a header but no fixture rows.",
                "Add the current Week 1 fixtures before entering odds.",
            )
        )
        return _finish(
            "Needs slate fixes", issues, matchweeks, notes, fixtures_path, fixture_count, today
        )

    parsed_dates = pd.to_datetime(fixtures["date"], errors="coerce", format="mixed")
    row_dates: list[date | None] = [
        value.date() if pd.notna(value) else None for value in parsed_dates
    ]

    for index, row in fixtures.iterrows():
        raw_date = _clean(row["date"])
        home = _clean(row["home_team"])
        away = _clean(row["away_team"])
        if row_dates[index] is None:
            issues.append(
                _issue(
                    "error",
                    "Invalid date",
                    f"Row {index + 2} has an unreadable date value '{raw_date}'.",
                    "Use YYYY-MM-DD dates in the fixture slate.",
                    fixture_date=raw_date,
                    home_team=home,
                    away_team=away,
                )
            )
        elif row_dates[index] < today:
            issues.append(
                _issue(
                    "warning",
                    "Past fixture",
                    f"Row {index + 2} is dated {row_dates[index].isoformat()}, which is in the past.",
                    "Remove played fixtures or refresh the slate to the upcoming matchweek.",
                    fixture_date=raw_date,
                    home_team=home,
                    away_team=away,
                )
            )
        if not home or not away:
            issues.append(
                _issue(
                    "error",
                    "Blank team",
                    f"Row {index + 2} has a blank home or away team.",
                    "Fill in both team names using Football-Data naming.",
                    fixture_date=raw_date,
                    home_team=home,
                    away_team=away,
                )
            )
        elif home == away:
            issues.append(
                _issue(
                    "error",
                    "Same team twice",
                    f"Row {index + 2} lists {home} as both home and away.",
                    "Correct one of the team names.",
                    fixture_date=raw_date,
                    home_team=home,
                    away_team=away,
                )
            )

    # Exact duplicate fixture rows.
    key_series = fixtures.apply(
        lambda row: (
            _clean(row["date"]),
            _clean(row["home_team"]),
            _clean(row["away_team"]),
        ),
        axis=1,
    )
    duplicate_mask = key_series.duplicated(keep="first")
    for index in fixtures.index[duplicate_mask]:
        raw_date, home, away = key_series[index]
        issues.append(
            _issue(
                "error",
                "Duplicate fixture",
                f"{home} vs {away} on {raw_date} appears more than once.",
                "Delete the duplicate fixture row.",
                fixture_date=raw_date,
                home_team=home,
                away_team=away,
            )
        )

    # Repeated pairing on different dates (suspicious this early in a season).
    pair_series = fixtures.apply(
        lambda row: (_clean(row["home_team"]), _clean(row["away_team"])), axis=1
    )
    repeated_pairs = {
        pair
        for pair in pair_series[pair_series.duplicated(keep=False)]
        if pair[0] and pair[1]
    }
    for home, away in sorted(repeated_pairs):
        dates_for_pair = sorted(
            {
                key[0]
                for key in key_series
                if (key[1], key[2]) == (home, away) and key[0]
            }
        )
        if len(dates_for_pair) > 1:
            issues.append(
                _issue(
                    "warning",
                    "Repeated pairing",
                    f"{home} vs {away} appears on multiple dates: "
                    + ", ".join(dates_for_pair),
                    "EPL pairings do not repeat this quickly; confirm one of these "
                    "dates against the official schedule.",
                    home_team=home,
                    away_team=away,
                )
            )

    # Matchweek grouping and double-booked teams.
    valid_dates = [value for value in row_dates if value is not None]
    groups = _assign_matchweek_groups(valid_dates)
    matchweek_rows: list[dict[str, object]] = []
    if groups:
        by_group: dict[int, list[int]] = {}
        for index, value in enumerate(row_dates):
            if value is not None:
                by_group.setdefault(groups[value], []).append(index)
        for group_id in sorted(by_group):
            indexes = by_group[group_id]
            group_dates = sorted(row_dates[index] for index in indexes)
            teams: list[str] = []
            for index in indexes:
                home = _clean(fixtures.iloc[index]["home_team"])
                away = _clean(fixtures.iloc[index]["away_team"])
                teams.extend(name for name in (home, away) if name)
            team_counts = pd.Series(teams).value_counts() if teams else pd.Series(dtype=int)
            double_booked = sorted(team_counts[team_counts > 1].index.tolist())
            for team in double_booked:
                issues.append(
                    _issue(
                        "error",
                        "Double-booked team",
                        f"{team} appears {int(team_counts[team])} times in matchweek "
                        f"group {group_id + 1} ({group_dates[0].isoformat()} to "
                        f"{group_dates[-1].isoformat()}).",
                        "A team can only play once per matchweek; fix the fixture "
                        "rows or the dates.",
                        home_team=team,
                    )
                )
            note = "Complete matchweek." if len(indexes) == FULL_MATCHWEEK_FIXTURES else (
                f"{len(indexes)} fixture(s); a full EPL matchweek has "
                f"{FULL_MATCHWEEK_FIXTURES}. A partial slate is fine if intentional."
            )
            if len(indexes) != FULL_MATCHWEEK_FIXTURES:
                issues.append(
                    _issue(
                        "info",
                        "Partial matchweek",
                        f"Matchweek group {group_id + 1} has {len(indexes)} fixture(s) "
                        f"instead of {FULL_MATCHWEEK_FIXTURES}.",
                        "Confirm the missing fixtures are intentional (postponements, "
                        "partial slate) against the official schedule.",
                    )
                )
            matchweek_rows.append(
                {
                    "matchweek_group": group_id + 1,
                    "first_date": group_dates[0].isoformat(),
                    "last_date": group_dates[-1].isoformat(),
                    "fixture_count": len(indexes),
                    "unique_teams": int(team_counts.size),
                    "double_booked_teams": ", ".join(double_booked),
                    "note": note,
                }
            )
    matchweeks = pd.DataFrame(matchweek_rows, columns=MATCHWEEK_COLUMNS)
    if len(matchweek_rows) > 1:
        issues.append(
            _issue(
                "info",
                "Multiple matchweek groups",
                f"The slate spans {len(matchweek_rows)} matchweek groups; the odds "
                "completeness gate requires real prices for every fixture in the "
                "slate before a card can generate.",
                "If sportsbooks have not posted the later matchweek's prices yet, "
                "preview deferring it with `python scripts/trim_upcoming_fixtures.py` "
                "so Week 1 is not blocked waiting on unposted odds.",
            )
        )

    # Team-name spelling cross-check against historical data.
    historical_teams, history_note = _load_historical_teams(matches_path)
    notes.append(history_note)
    if historical_teams:
        slate_teams = sorted(
            {
                _clean(team)
                for column in ("home_team", "away_team")
                for team in fixtures[column].tolist()
                if _clean(team)
            }
        )
        for team in slate_teams:
            if team not in historical_teams:
                issues.append(
                    _issue(
                        "warning",
                        "Unknown team name",
                        f"{team} does not appear in the historical match data.",
                        "Newly promoted teams are expected to be missing; otherwise "
                        "fix the spelling to match Football-Data naming so the model "
                        "recognizes the team.",
                        home_team=team,
                    )
                )

    # Read-only cross-check against the existing odds file.
    odds_keys, odds_note = _load_odds_fixture_keys(current_odds_path)
    notes.append(odds_note)
    if odds_keys is not None:
        slate_keys = set(key_series)
        for raw_date, home, away in sorted(slate_keys - odds_keys):
            issues.append(
                _issue(
                    "warning",
                    "Fixture missing from odds file",
                    f"{home} vs {away} on {raw_date} has no rows in the odds file.",
                    "Run `python scripts/maintain_current_odds.py` to preview adding "
                    "the missing rows.",
                    fixture_date=raw_date,
                    home_team=home,
                    away_team=away,
                )
            )
        for raw_date, home, away in sorted(odds_keys - slate_keys):
            issues.append(
                _issue(
                    "warning",
                    "Odds rows without a slate fixture",
                    f"The odds file has rows for {home} vs {away} on {raw_date}, "
                    "which is not in the fixture slate.",
                    "Confirm whether the slate or the odds file is out of date "
                    "before trusting either.",
                    fixture_date=raw_date,
                    home_team=home,
                    away_team=away,
                )
            )

    severities = {item["severity"] for item in issues}
    if "error" in severities:
        status = "Needs slate fixes"
    elif "warning" in severities:
        status = "Slate ready with warnings"
    else:
        status = "Slate ready for manual confirmation"
    return _finish(status, issues, matchweeks, notes, fixtures_path, fixture_count, today)


def _finish(
    status: str,
    issues: list[dict[str, str]],
    matchweeks: pd.DataFrame,
    notes: list[str],
    fixtures_path: Path,
    fixture_count: int,
    today: date,
) -> dict[str, object]:
    if status not in SLATE_STATUSES:
        raise ValueError(f"Unexpected fixture slate status: {status}")
    issue_frame = pd.DataFrame(issues, columns=ISSUE_COLUMNS)
    counts = issue_frame["severity"].value_counts().to_dict() if not issue_frame.empty else {}
    summary = {
        "status": status,
        "checked_on": today.isoformat(),
        "fixtures_path": str(fixtures_path),
        "fixture_count": fixture_count,
        "matchweek_group_count": int(len(matchweeks)),
        "error_count": int(counts.get("error", 0)),
        "warning_count": int(counts.get("warning", 0)),
        "info_count": int(counts.get("info", 0)),
        "notes": [note for note in notes if note],
        "confirmation_checklist": list(CONFIRMATION_CHECKLIST),
    }
    return {"status": status, "summary": summary, "issues": issue_frame, "matchweeks": matchweeks}


def render_fixture_slate_markdown(result: dict[str, object]) -> str:
    summary = result["summary"]
    issues: pd.DataFrame = result["issues"]
    matchweeks: pd.DataFrame = result["matchweeks"]
    lines = [
        "# Fixture Slate Confirmation Report",
        "",
        (
            "This report only reads the fixture slate, historical matches, and the "
            "odds file. It never edits fixtures or odds, never fabricates prices, "
            "and never places bets. A ready verdict still requires a human to "
            "confirm the slate against the official EPL schedule."
        ),
        "",
        "## Verdict",
        "",
        f"- Status: **{summary['status']}**",
        f"- Checked on: {summary['checked_on']}",
        f"- Fixture file: `{summary['fixtures_path']}`",
        f"- Fixtures: {summary['fixture_count']}",
        (
            f"- Issues: {summary['error_count']} error(s), "
            f"{summary['warning_count']} warning(s), "
            f"{summary['info_count']} informational note(s)."
        ),
        "",
        "## Matchweek groups",
        "",
        matchweeks.to_markdown(index=False)
        if not matchweeks.empty
        else "No valid fixture dates were available to group.",
        "",
        "## Issues",
        "",
        issues.to_markdown(index=False) if not issues.empty else "No issues found.",
        "",
        "## Notes",
        "",
    ]
    lines.extend([f"- {note}" for note in summary["notes"]] or ["- None."])
    lines.extend(["", "## Manual confirmation checklist", ""])
    lines.extend([f"- [ ] {item}" for item in summary["confirmation_checklist"]])
    return "\n".join(lines)


def save_fixture_slate_check(
    result: dict[str, object],
    output_dir: Path | None = None,
) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    issues: pd.DataFrame = result["issues"]
    payload = {
        "summary": result["summary"],
        "matchweeks": result["matchweeks"].to_dict(orient="records"),
        "issues": issues.to_dict(orient="records"),
    }
    json_path = output_dir / SLATE_CHECK_JSON_FILENAME
    markdown_path = output_dir / SLATE_CHECK_MARKDOWN_FILENAME
    csv_path = output_dir / SLATE_CHECK_CSV_FILENAME
    atomic_write_report(
        json_path,
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    atomic_write_report(
        markdown_path,
        (render_fixture_slate_markdown(result) + "\n").encode("utf-8"),
    )
    atomic_write_report(csv_path, issues.to_csv(index=False).encode("utf-8"))
    return {"json": json_path, "markdown": markdown_path, "csv": csv_path}


def run_fixture_slate_check(
    fixtures_path: Path | None = None,
    *,
    matches_path: Path | None = None,
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    today: date | None = None,
) -> dict[str, object]:
    result = build_fixture_slate_check(
        fixtures_path,
        matches_path=matches_path,
        current_odds_path=current_odds_path,
        today=today,
    )
    result["paths"] = save_fixture_slate_check(result, output_dir)
    return result
