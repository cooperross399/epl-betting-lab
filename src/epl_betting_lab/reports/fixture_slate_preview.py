from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR


SLATE_STATUSES = {
    "Slate ready",
    "Empty slate",
    "Needs fixture refresh",
    "Fixture date issues",
    "Fixture team issues",
    "Duplicate fixtures",
    "Blocked",
}
MATCHWEEK_COLUMNS = ("matchweek", "week")
DEFAULT_MAX_DATE_GAP_DAYS = 3
PREVIEW_COLUMNS = [
    "slate_status",
    "selection_mode",
    "target_matchweek_label",
    "selected_date_from",
    "selected_date_to",
    "row_number",
    "date",
    "home_team",
    "away_team",
    "matchweek",
    "disposition",
    "reason",
    "in_selected_scope",
    "is_past",
    "has_date_issue",
    "has_team_issue",
    "is_duplicate",
]


def _now_iso(now: datetime | None) -> str:
    value = now or datetime.now().astimezone()
    if value.tzinfo is None:
        value = value.astimezone()
    return value.isoformat(timespec="seconds")


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _date_text(value: date | None) -> str:
    return value.isoformat() if value is not None else ""


def _json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return json.loads(frame.where(pd.notna(frame), "").to_json(orient="records"))


def _base_summary(
    fixtures_path: Path,
    *,
    today: date,
    date_from: date | None,
    date_to: date | None,
    matchweek: str | None,
    now: datetime | None,
) -> dict[str, Any]:
    return {
        "report": "Week 1 Fixture Slate Preview",
        "generated_at": _now_iso(now),
        "as_of_date": today.isoformat(),
        "fixtures_path": str(fixtures_path),
        "status": "Blocked",
        "selection_mode": "Not checked",
        "requested_date_from": _date_text(date_from),
        "requested_date_to": _date_text(date_to),
        "requested_matchweek": _clean(matchweek),
        "target_matchweek_label": "",
        "matchweek_column": "",
        "available_matchweeks": [],
        "available_fields": [],
        "selected_date_from": "",
        "selected_date_to": "",
        "fixture_count": 0,
        "included_fixture_count": 0,
        "excluded_past_fixture_count": 0,
        "excluded_future_fixture_count": 0,
        "malformed_date_count": 0,
        "missing_team_count": 0,
        "selected_missing_team_count": 0,
        "duplicate_fixture_count": 0,
        "selected_duplicate_fixture_count": 0,
        "fixture_issue_count": 0,
        "earliest_fixture_date": "",
        "latest_fixture_date": "",
        "first_fixture": "",
        "last_fixture": "",
        "template_eligible": False,
        "template_created_from_slate": False,
        "template_path": "",
        "status_reason": "The fixture slate has not been checked yet.",
        "next_human_action": "Check the fixture source before creating an odds template.",
    }


def _empty_rows() -> pd.DataFrame:
    return pd.DataFrame(columns=PREVIEW_COLUMNS)


def _result(
    summary: dict[str, Any],
    rows: pd.DataFrame | None = None,
    included: pd.DataFrame | None = None,
) -> dict[str, object]:
    if summary["status"] not in SLATE_STATUSES:
        raise ValueError(f"Unsupported fixture slate status: {summary['status']}")
    return {
        "status": summary["status"],
        "summary": summary,
        "rows": rows if rows is not None else _empty_rows(),
        "included_fixtures": included if included is not None else pd.DataFrame(),
    }


def _blocked(
    summary: dict[str, Any],
    reason: str,
    action: str,
) -> dict[str, object]:
    summary.update(
        {
            "status": "Blocked",
            "status_reason": reason,
            "next_human_action": action,
        }
    )
    return _result(summary)


def _default_date_window(valid_future_dates: list[date]) -> tuple[date, date]:
    dates = sorted(set(valid_future_dates))
    start = dates[0]
    end = start
    for candidate in dates[1:]:
        if (candidate - end).days > DEFAULT_MAX_DATE_GAP_DAYS:
            break
        end = candidate
    return start, end


def _fixture_label(row: pd.Series) -> str:
    return f"{_clean(row.get('date'))}: {_clean(row.get('home_team'))} vs {_clean(row.get('away_team'))}"


def build_fixture_slate_preview(
    fixtures_path: Path | None = None,
    *,
    today: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    matchweek: str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Select one fixture slate without creating an odds file or running the model."""
    fixtures_path = fixtures_path or MANUAL_DIR / "upcoming_fixtures.csv"
    today = today or date.today()
    requested_matchweek = _clean(matchweek)
    summary = _base_summary(
        fixtures_path,
        today=today,
        date_from=date_from,
        date_to=date_to,
        matchweek=requested_matchweek,
        now=now,
    )

    if date_from and date_to and date_from > date_to:
        return _blocked(
            summary,
            "The requested start date is after the requested end date.",
            "Choose a valid inclusive date range, then rerun the preview.",
        )
    if not fixtures_path.exists():
        return _blocked(
            summary,
            f"Missing fixture file: {fixtures_path}.",
            "Add upcoming fixtures before previewing or creating an odds template.",
        )

    try:
        fixtures = pd.read_csv(fixtures_path, dtype=str).fillna("")
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        return _blocked(
            summary,
            f"The fixture CSV could not be read: {exc}",
            "Fix the fixture CSV, then rerun the preview.",
        )

    summary["available_fields"] = list(fixtures.columns)
    summary["fixture_count"] = int(len(fixtures))
    if fixtures.empty:
        summary.update(
            {
                "status": "Empty slate",
                "selection_mode": "Source file",
                "status_reason": "The fixture file has no rows.",
                "next_human_action": "Add current Week 1 fixtures, then rerun the preview.",
            }
        )
        return _result(summary)

    required = {"date", "home_team", "away_team"}
    missing_columns = sorted(required - set(fixtures.columns))
    if missing_columns:
        return _blocked(
            summary,
            f"Missing required fixture column(s): {', '.join(missing_columns)}.",
            "Add date, home_team, and away_team columns before previewing the slate.",
        )

    matchweek_column = next(
        (column for column in MATCHWEEK_COLUMNS if column in fixtures.columns),
        "",
    )
    summary["matchweek_column"] = matchweek_column
    if matchweek_column:
        available_matchweeks = sorted(
            {
                _clean(value)
                for value in fixtures[matchweek_column]
                if _clean(value)
            }
        )
        summary["available_matchweeks"] = available_matchweeks
    if requested_matchweek and not matchweek_column:
        return _blocked(
            summary,
            (
                f"Matchweek `{requested_matchweek}` was requested, but the fixture file has no "
                f"matchweek/week column. Available fields: {', '.join(fixtures.columns)}."
            ),
            "Use --date-from/--date-to or add a matchweek column to the fixture file.",
        )

    parsed_dates = pd.to_datetime(fixtures["date"], format="%Y-%m-%d", errors="coerce")
    fixture_dates = parsed_dates.dt.date
    date_issue_mask = parsed_dates.isna()
    past_mask = parsed_dates.notna() & fixture_dates.lt(today)
    future_mask = parsed_dates.notna() & fixture_dates.ge(today)
    team_issue_mask = (
        fixtures["home_team"].astype(str).str.strip().eq("")
        | fixtures["away_team"].astype(str).str.strip().eq("")
    )

    valid_dates = list(fixture_dates[parsed_dates.notna()])
    if valid_dates:
        summary["earliest_fixture_date"] = min(valid_dates).isoformat()
        summary["latest_fixture_date"] = max(valid_dates).isoformat()

    normalized_date = parsed_dates.dt.strftime("%Y-%m-%d").fillna("")
    duplicate_keys = pd.DataFrame(
        {
            "date": normalized_date,
            "home_team": fixtures["home_team"].astype(str).str.strip().str.lower(),
            "away_team": fixtures["away_team"].astype(str).str.strip().str.lower(),
        }
    )
    duplicate_mask = (
        duplicate_keys.duplicated(keep=False)
        & ~date_issue_mask
        & ~team_issue_mask
    )

    in_scope = pd.Series(False, index=fixtures.index, dtype=bool)
    selected_from = date_from
    selected_to = date_to
    target_matchweek = requested_matchweek

    if requested_matchweek:
        summary["selection_mode"] = "Matchweek"
        label_mask = fixtures[matchweek_column].astype(str).str.strip().eq(requested_matchweek)
        in_scope = label_mask & parsed_dates.notna()
        if date_from:
            in_scope &= fixture_dates.ge(date_from)
        if date_to:
            in_scope &= fixture_dates.le(date_to)
    elif date_from or date_to:
        summary["selection_mode"] = "Date window"
        in_scope = parsed_dates.notna()
        if date_from:
            in_scope &= fixture_dates.ge(date_from)
        if date_to:
            in_scope &= fixture_dates.le(date_to)
    elif future_mask.any():
        earliest_future_index = parsed_dates[future_mask].idxmin()
        earliest_label = (
            _clean(fixtures.loc[earliest_future_index, matchweek_column])
            if matchweek_column
            else ""
        )
        if earliest_label:
            summary["selection_mode"] = "Next upcoming matchweek"
            target_matchweek = earliest_label
            in_scope = (
                fixtures[matchweek_column].astype(str).str.strip().eq(earliest_label)
                & parsed_dates.notna()
            )
        else:
            summary["selection_mode"] = "Next upcoming date cluster"
            selected_from, selected_to = _default_date_window(list(fixture_dates[future_mask]))
            in_scope = (
                parsed_dates.notna()
                & fixture_dates.ge(selected_from)
                & fixture_dates.le(selected_to)
            )
    else:
        summary["selection_mode"] = "Next upcoming slate"

    summary["target_matchweek_label"] = target_matchweek
    scoped_dates = list(fixture_dates[in_scope & parsed_dates.notna()])
    if selected_from is None and scoped_dates:
        selected_from = min(scoped_dates)
    if selected_to is None and scoped_dates:
        selected_to = max(scoped_dates)
    summary["selected_date_from"] = _date_text(selected_from)
    summary["selected_date_to"] = _date_text(selected_to)

    selected_team_issues = in_scope & team_issue_mask & future_mask
    selected_duplicates = in_scope & duplicate_mask & future_mask
    included_mask = (
        in_scope
        & future_mask
        & ~team_issue_mask
        & ~duplicate_mask
    )

    dispositions: list[str] = []
    reasons: list[str] = []
    for index in fixtures.index:
        if date_issue_mask.loc[index]:
            disposition = "Fixture date issue"
            reason = "The fixture date is blank or malformed."
        elif past_mask.loc[index]:
            disposition = "Excluded past"
            reason = "The fixture is before the local readiness date."
        elif not in_scope.loc[index]:
            disposition = "Excluded future"
            reason = "The fixture is outside the selected slate/window."
        elif team_issue_mask.loc[index]:
            disposition = "Fixture team issue"
            reason = "The selected fixture is missing a home or away team."
        elif duplicate_mask.loc[index]:
            disposition = "Duplicate fixture"
            reason = "The selected date/home/away fixture appears more than once."
        else:
            disposition = "Included"
            reason = "Included in the confirmed slate used for odds readiness."
        dispositions.append(disposition)
        reasons.append(reason)

    rows = pd.DataFrame(
        {
            "row_number": fixtures.index.to_series().astype(int) + 2,
            "date": fixtures["date"],
            "home_team": fixtures["home_team"],
            "away_team": fixtures["away_team"],
            "matchweek": (
                fixtures[matchweek_column]
                if matchweek_column
                else pd.Series("", index=fixtures.index)
            ),
            "disposition": dispositions,
            "reason": reasons,
            "in_selected_scope": in_scope,
            "is_past": past_mask,
            "has_date_issue": date_issue_mask,
            "has_team_issue": team_issue_mask,
            "is_duplicate": duplicate_mask,
        }
    )
    included = fixtures.loc[included_mask].copy()
    if not included.empty:
        included["date"] = parsed_dates.loc[included.index].dt.strftime("%Y-%m-%d")
        included = included.sort_values(
            ["date", "home_team", "away_team"], kind="stable"
        ).reset_index(drop=True)

    summary.update(
        {
            "included_fixture_count": int(included_mask.sum()),
            "excluded_past_fixture_count": int((rows["disposition"] == "Excluded past").sum()),
            "excluded_future_fixture_count": int((rows["disposition"] == "Excluded future").sum()),
            "malformed_date_count": int(date_issue_mask.sum()),
            "missing_team_count": int(team_issue_mask.sum()),
            "selected_missing_team_count": int(selected_team_issues.sum()),
            "duplicate_fixture_count": int(duplicate_mask.sum()),
            "selected_duplicate_fixture_count": int(selected_duplicates.sum()),
        }
    )
    summary["fixture_issue_count"] = (
        int(summary["malformed_date_count"])
        + int(summary["selected_missing_team_count"])
        + int(summary["selected_duplicate_fixture_count"])
    )
    if not included.empty:
        summary["first_fixture"] = _fixture_label(included.iloc[0])
        summary["last_fixture"] = _fixture_label(included.iloc[-1])

    selected_past_count = int((in_scope & past_mask).sum())
    selected_row_count = int(in_scope.sum())
    if summary["malformed_date_count"]:
        status = "Fixture date issues"
        reason = f"{summary['malformed_date_count']} fixture date row(s) are blank or malformed."
        action = "Fix every fixture date before creating the odds template."
    elif summary["selected_missing_team_count"]:
        status = "Fixture team issues"
        reason = f"{summary['selected_missing_team_count']} selected fixture row(s) have a missing team."
        action = "Fill the missing home/away teams, then rerun the preview."
    elif summary["selected_duplicate_fixture_count"]:
        status = "Duplicate fixtures"
        reason = f"{summary['selected_duplicate_fixture_count']} selected fixture row(s) are duplicates."
        action = "Remove or correct duplicate fixtures, then rerun the preview."
    elif int(summary["included_fixture_count"]):
        status = "Slate ready"
        reason = f"{summary['included_fixture_count']} upcoming fixture(s) are confirmed for this slate."
        action = "Confirm the included matches, then fill real odds or create the missing blank template."
    elif selected_past_count or (not future_mask.any() and bool(valid_dates)):
        status = "Needs fixture refresh"
        reason = "The selected fixture slate is all in the past."
        action = "Refresh upcoming_fixtures.csv with current matches before creating an odds template."
    else:
        status = "Empty slate"
        available = (
            f" Available matchweeks: {', '.join(summary['available_matchweeks'])}."
            if summary["available_matchweeks"]
            else ""
        )
        reason = "No fixtures matched the selected slate/window." + available
        action = "Adjust the matchweek/date window or refresh the fixture file, then preview again."

    summary.update(
        {
            "status": status,
            "template_eligible": status == "Slate ready",
            "status_reason": reason,
            "next_human_action": action,
            "selected_row_count": selected_row_count,
            "selected_past_fixture_count": selected_past_count,
        }
    )
    for column, value in {
        "slate_status": status,
        "selection_mode": summary["selection_mode"],
        "target_matchweek_label": target_matchweek,
        "selected_date_from": summary["selected_date_from"],
        "selected_date_to": summary["selected_date_to"],
    }.items():
        rows.insert(0, column, value)
    rows = rows[PREVIEW_COLUMNS]
    return _result(summary, rows, included)


def render_fixture_slate_preview(
    summary: dict[str, object],
    rows: pd.DataFrame,
) -> str:
    included = rows[rows["disposition"] == "Included"] if not rows.empty else rows
    excluded = rows[rows["disposition"] != "Included"] if not rows.empty else rows
    display_columns = [
        "date",
        "home_team",
        "away_team",
        "matchweek",
        "disposition",
        "reason",
    ]
    window = (
        f"{summary.get('selected_date_from') or 'Open'} to "
        f"{summary.get('selected_date_to') or 'Open'}"
    )
    lines = [
        "# Week 1 Fixture Slate Preview",
        "",
        "This preview reads upcoming fixtures and selects the slate used for blank odds-template generation. It does not fetch or invent odds, edit an existing odds file, run the model, or place bets.",
        "",
        "## Slate summary",
        "",
        f"- Selected slate status: **{summary['status']}**",
        f"- Selection mode: **{summary['selection_mode']}**",
        f"- Target matchweek: **{summary.get('target_matchweek_label') or 'Not available'}**",
        f"- Selected date window: **{window}**",
        f"- Included fixtures: **{int(summary['included_fixture_count'])}**",
        f"- Excluded past fixtures: **{int(summary['excluded_past_fixture_count'])}**",
        f"- Excluded future fixtures: **{int(summary['excluded_future_fixture_count'])}**",
        f"- Malformed dates: **{int(summary['malformed_date_count'])}**",
        f"- Selected missing-team rows: **{int(summary['selected_missing_team_count'])}**",
        f"- Selected duplicate rows: **{int(summary['selected_duplicate_fixture_count'])}**",
        f"- First fixture: **{summary.get('first_fixture') or 'Not available'}**",
        f"- Last fixture: **{summary.get('last_fixture') or 'Not available'}**",
        f"- Odds template created from this slate: **{'Yes' if summary.get('template_created_from_slate') else 'No'}**",
        "",
        "## Included matches",
        "",
        included[display_columns].to_markdown(index=False)
        if not included.empty
        else "No matches are currently safe to include.",
        "",
        "## Excluded matches and issues",
        "",
        excluded[display_columns].to_markdown(index=False)
        if not excluded.empty
        else "No fixtures were excluded and no fixture issues were found.",
        "",
        "## Exact next human action",
        "",
        str(summary["next_human_action"]),
        "",
        "A ready slate is only permission to create a blank template. Real sportsbook prices must still be entered manually before the weekly pipeline can generate a card.",
    ]
    return "\n".join(lines)


def save_fixture_slate_preview(
    preview: dict[str, object],
    output_dir: Path | None = None,
) -> dict[str, object]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = preview["summary"]
    rows = preview["rows"]
    if not isinstance(summary, dict) or not isinstance(rows, pd.DataFrame):
        raise TypeError("Fixture slate preview must contain summary and rows data.")

    csv_path = output_dir / "fixture_slate_preview.csv"
    markdown_path = output_dir / "fixture_slate_preview.md"
    json_path = output_dir / "fixture_slate_preview.json"
    rows.to_csv(csv_path, index=False)
    markdown_path.write_text(render_fixture_slate_preview(summary, rows), encoding="utf-8")
    payload = dict(summary)
    payload["fixtures"] = _json_records(rows)
    payload["output_files"] = {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "csv": str(csv_path),
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": summary["status"],
        "summary": summary,
        "rows": rows,
        "included_fixtures": preview["included_fixtures"],
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
    }


def generate_fixture_slate_preview(
    fixtures_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    today: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    matchweek: str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    preview = build_fixture_slate_preview(
        fixtures_path,
        today=today,
        date_from=date_from,
        date_to=date_to,
        matchweek=matchweek,
        now=now,
    )
    return save_fixture_slate_preview(preview, output_dir)
