from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.current_odds_completeness import (
    COMPLETENESS_COLUMNS,
    build_current_odds_completeness,
    render_current_odds_completeness_report,
)
from epl_betting_lab.reports.current_odds_template import create_current_odds_template
from epl_betting_lab.reports.current_odds_validation import (
    VALIDATION_COLUMNS,
    build_current_odds_validation,
    render_current_odds_validation_report,
)
from epl_betting_lab.selected_slate import (
    filter_to_selected_window,
    frame_window_label,
    outside_selected_window,
)
from epl_betting_lab.workflow_status import (
    CurrentOddsDateFreshness,
    FixtureDateFreshness,
    inspect_current_odds_date_freshness,
    inspect_fixture_date_freshness,
)


READINESS_STATUSES = {
    "Ready for weekly pipeline",
    "Needs odds filled",
    "Needs fixture refresh",
    "Needs odds fixes",
    "Missing fixtures",
    "Blocked",
    "Failed",
}

ATTENTION_COLUMNS = [
    "final_readiness_status",
    "fixture_status",
    "odds_file_status",
    "odds_completeness_percentage",
    "missing_odds_count",
    "invalid_odds_issue_count",
    "stale_odds_row_count",
    "category",
    "severity",
    "issue",
    "row_number",
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "book",
    "current_value",
    "recommended_action",
    "details",
]

MISSING_ODDS_ISSUES = {"missing_american_odds", "missing_expected_market_row"}
VALIDATION_DUPLICATES_FROM_COMPLETENESS = {
    "missing_american_odds",
    "non_numeric_american_odds",
    "duplicate_row",
}


def _now_iso(now: datetime | None) -> str:
    value = now or datetime.now().astimezone()
    if value.tzinfo is None:
        value = value.astimezone()
    return value.isoformat(timespec="seconds")


def _clean(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _json_records(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    return json.loads(frame.where(pd.notna(frame), "").to_json(orient="records"))


def _attention_row(
    *,
    category: str,
    severity: str,
    issue: str,
    recommended_action: str,
    details: str,
    source: pd.Series | None = None,
    current_value: object = "",
) -> dict[str, object]:
    source = source if source is not None else pd.Series(dtype=object)
    return {
        "category": category,
        "severity": severity,
        "issue": issue,
        "row_number": source.get("row_number", ""),
        "date": source.get("date", ""),
        "home_team": source.get("home_team", ""),
        "away_team": source.get("away_team", ""),
        "market": source.get("market", ""),
        "selection": source.get("selection", ""),
        "book": source.get("book", ""),
        "current_value": current_value,
        "recommended_action": recommended_action,
        "details": details,
    }


def _fixture_status_text(freshness: FixtureDateFreshness) -> str:
    if freshness.status == "Fresh":
        return f"Fresh ({freshness.today_or_future_fixtures or 0} upcoming match(es))"
    return freshness.status or "Not checked"


def _odds_status_text(
    freshness: CurrentOddsDateFreshness,
    *,
    template_created: bool,
    template_overwritten: bool,
) -> str:
    if template_overwritten:
        return "Blank template replaced by explicit Terminal flag"
    if template_created:
        return "Blank template created"
    if freshness.status == "Fresh":
        return f"Existing file preserved ({freshness.today_or_future_rows or 0} current row(s))"
    return f"Existing file preserved ({freshness.status or 'Not checked'})"


def _weekly_pipeline_likelihood(status: str, warning_count: int) -> str:
    if status == "Ready for weekly pipeline":
        return "Card generated with warnings" if warning_count else "Ready for card review"
    if status == "Needs odds filled":
        return "Needs odds"
    if status == "Needs odds fixes":
        return "Needs odds fixes"
    if status in {"Needs fixture refresh", "Missing fixtures"}:
        return "Needs data refresh"
    return "Blocked"


def _next_action(status: str, *, template_created: bool, missing_books: int) -> str:
    if status == "Ready for weekly pipeline":
        book_note = (
            f" Review the {missing_books} blank book name(s) when available."
            if missing_books
            else ""
        )
        return (
            "Run `python scripts/run_epl_weekly_pipeline.py`, then manually review the card."
            + book_note
        )
    if status == "Needs odds filled":
        created_note = "The blank template is ready. " if template_created else ""
        return (
            f"{created_note}Enter real sportsbook prices in `american_odds` and add book names, "
            "then rerun this readiness command."
        )
    if status == "Needs fixture refresh":
        return (
            "Refresh `data/manual/upcoming_fixtures.csv` with current Week 1/upcoming matches, "
            "then rerun this command."
        )
    if status == "Missing fixtures":
        return (
            "Create `data/manual/upcoming_fixtures.csv` with current Week 1 fixtures before "
            "creating or filling the odds template."
        )
    if status == "Needs odds fixes":
        return (
            "Fix the listed invalid, duplicate, non-numeric, stale, or date-problem odds rows, "
            "then rerun this readiness command."
        )
    if status == "Failed":
        return "Read the failure details below, fix the unexpected error, and rerun the command."
    return "Fix the unreadable or malformed input shown below, then rerun the command."


def _render_markdown(summary: dict[str, object], attention: pd.DataFrame) -> str:
    missing_rows = attention[attention["category"] == "Missing odds"] if not attention.empty else attention
    invalid_rows = attention[
        attention["category"].isin(["Odds fix", "Stale odds", "Odds date fix"])
    ] if not attention.empty else attention
    fixture_rows = attention[attention["category"] == "Fixtures"] if not attention.empty else attention
    missing_books = attention[attention["category"] == "Missing book"] if not attention.empty else attention
    table_columns = [
        "date",
        "home_team",
        "away_team",
        "market",
        "selection",
        "book",
        "issue",
        "recommended_action",
    ]

    lines = [
        "# Week 1 Launch Readiness",
        "",
        "This setup checks fixtures and real manual odds. It may create a missing blank odds template, but it never invents prices, places bets, runs live providers, applies settlement, allowlists providers, or enables cron.",
        "",
        "## Launch summary",
        "",
        f"- Final readiness status: **{summary['status']}**",
        f"- Fixture status: **{summary['fixture_status']}**",
        f"- Odds file status: **{summary['odds_file_status']}**",
        f"- Odds completeness: **{float(summary['odds_completeness_percentage']):.1%}**",
        f"- Missing odds rows: **{int(summary['missing_odds_count'])}**",
        f"- Invalid odds issues: **{int(summary['invalid_odds_issue_count'])}**",
        f"- Missing book names: **{int(summary['missing_book_count'])}**",
        f"- Stale/past odds rows: **{int(summary['stale_odds_row_count'])}**",
        f"- Likely weekly pipeline result: **{summary['likely_weekly_pipeline_status']}**",
        f"- Run the weekly pipeline next: **{'Yes' if summary['run_weekly_pipeline_next'] else 'No'}**",
        "",
        "## Exact next human action",
        "",
        str(summary["next_human_action"]),
        "",
        "## Fixtures",
        "",
        f"- File: `{summary['fixtures_path']}`",
        f"- Upcoming matches found: {int(summary['upcoming_fixture_count'])}",
        f"- Selected Week 1 window: **{summary['selected_window']}**",
        (
            "- Matches inside the selected Week 1 window: "
            f"**{int(summary['selected_window_fixture_count'])}**"
        ),
        (
            "- Upcoming matches outside that window (later round): "
            f"**{int(summary['fixtures_outside_selected_window_count'])}**"
        ),
        (
            "- Matchweek column available: "
            f"{'Yes' if summary['matchweek_column_available'] else 'No (window used instead)'}"
        ),
        f"- Week 1 matches counted: {int(summary['week1_fixture_count'])}",
        f"- Earliest fixture date: {summary['earliest_fixture_date'] or 'Not available'}",
        f"- Latest fixture date: {summary['latest_fixture_date'] or 'Not available'}",
        f"- Fixture note: {summary['fixture_note']}",
        "",
    ]
    slate_warnings = summary.get("slate_warnings") or []
    if slate_warnings:
        lines.extend(
            [
                "## Slate window warnings",
                "",
                *[f"- {warning}" for warning in slate_warnings],
                "",
                (
                    "No protected file was modified. Re-scoping the slate or the "
                    "odds template is a deliberate human decision."
                ),
                "",
            ]
        )
        outside = summary.get("fixtures_outside_selected_window") or []
        if outside:
            lines.extend(
                [
                    "Fixtures outside the selected Week 1 window:",
                    "",
                    *[f"- {item}" for item in outside],
                    "",
                ]
            )
    if not fixture_rows.empty:
        lines.extend([fixture_rows[table_columns].to_markdown(index=False), ""])

    lines.extend(["## Odds still needed", ""])
    lines.append(
        missing_rows[table_columns].to_markdown(index=False)
        if not missing_rows.empty
        else "No missing fixture/market odds rows found."
    )
    lines.extend(["", "## Odds fixes and stale rows", ""])
    lines.append(
        invalid_rows[table_columns].to_markdown(index=False)
        if not invalid_rows.empty
        else "No invalid or stale odds rows found."
    )
    lines.extend(["", "## Missing book names", ""])
    lines.append(
        missing_books[table_columns].to_markdown(index=False)
        if not missing_books.empty
        else "No missing book names found."
    )
    lines.extend(
        [
            "",
            "## Safe commands",
            "",
            "Rerun Week 1 readiness:",
            "",
            "```bash",
            "python scripts/run_week1_launch_readiness.py",
            "```",
            "",
            "Run the weekly pipeline only after this report says Ready for weekly pipeline:",
            "",
            "```bash",
            "python scripts/run_epl_weekly_pipeline.py",
            "```",
            "",
            "An existing `current_odds.csv` was not overwritten unless the Terminal-only `--overwrite-template` flag was explicitly supplied. The dashboard never supplies that flag.",
        ]
    )
    return "\n".join(lines)


def _write_outputs(
    summary: dict[str, object],
    attention_rows: list[dict[str, object]],
    output_dir: Path,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    attention = pd.DataFrame(attention_rows)
    if attention.empty:
        attention = pd.DataFrame(
            [
                {
                    "category": "Summary",
                    "severity": "info",
                    "issue": "no_blocking_launch_issues",
                    "row_number": "",
                    "date": "",
                    "home_team": "",
                    "away_team": "",
                    "market": "",
                    "selection": "",
                    "book": "",
                    "current_value": "",
                    "recommended_action": summary["next_human_action"],
                    "details": "Week 1 inputs passed the launch-readiness checks.",
                }
            ]
        )

    for column, value in {
        "final_readiness_status": summary["status"],
        "fixture_status": summary["fixture_status"],
        "odds_file_status": summary["odds_file_status"],
        "odds_completeness_percentage": summary["odds_completeness_percentage"],
        "missing_odds_count": summary["missing_odds_count"],
        "invalid_odds_issue_count": summary["invalid_odds_issue_count"],
        "stale_odds_row_count": summary["stale_odds_row_count"],
    }.items():
        attention.insert(len(attention.columns), column, value)
    attention = attention[ATTENTION_COLUMNS]

    csv_path = output_dir / "week1_launch_readiness.csv"
    markdown_path = output_dir / "week1_launch_readiness.md"
    json_path = output_dir / "week1_launch_readiness.json"
    attention.to_csv(csv_path, index=False)

    summary["attention_rows"] = _json_records(attention)
    summary["output_files"] = {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "csv": str(csv_path),
    }
    markdown_path.write_text(_render_markdown(summary, attention), encoding="utf-8")
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "status": summary["status"],
        "summary": summary,
        "json": json_path,
        "markdown": markdown_path,
        "csv": csv_path,
    }


def _base_summary(
    *,
    fixtures_path: Path,
    odds_path: Path,
    today: date,
    now: datetime | None,
) -> dict[str, Any]:
    return {
        "report": "Week 1 Launch Readiness",
        "generated_at": _now_iso(now),
        "as_of_date": today.isoformat(),
        "status": "Blocked",
        "fixture_status": "Not checked",
        "fixture_note": "Fixture checks have not run yet.",
        "fixtures_path": str(fixtures_path),
        "upcoming_fixture_count": 0,
        "week1_fixture_count": 0,
        "selected_window": "no dated fixtures",
        "selected_window_fixture_count": 0,
        "fixtures_outside_selected_window_count": 0,
        "fixtures_outside_selected_window": [],
        "odds_rows_outside_selected_window_count": 0,
        "odds_matches_outside_selected_window": [],
        "matchweek_column_available": False,
        "slate_warnings": [],
        "earliest_fixture_date": "",
        "latest_fixture_date": "",
        "past_fixture_count": 0,
        "invalid_fixture_date_count": 0,
        "odds_file_status": "Not checked",
        "current_odds_path": str(odds_path),
        "template_created": False,
        "template_overwritten": False,
        "template_row_count": 0,
        "odds_completeness_percentage": 0.0,
        "missing_odds_count": 0,
        "invalid_odds_issue_count": 0,
        "validation_warning_count": 0,
        "missing_book_count": 0,
        "stale_odds_row_count": 0,
        "current_odds_row_count": 0,
        "invalid_odds_date_row_count": 0,
        "earliest_odds_date": "",
        "latest_odds_date": "",
        "likely_weekly_pipeline_status": "Blocked",
        "run_weekly_pipeline_next": False,
        "weekly_pipeline_command": "python scripts/run_epl_weekly_pipeline.py",
        "next_human_action": "Complete the launch checks before running the weekly pipeline.",
        "validation_report_paths": {},
        "completeness_report_paths": {},
    }


def _finish(
    summary: dict[str, Any],
    attention: list[dict[str, object]],
    output_dir: Path,
    *,
    status: str,
) -> dict[str, object]:
    if status not in READINESS_STATUSES:
        raise ValueError(f"Unsupported Week 1 readiness status: {status}")
    summary["status"] = status
    summary["likely_weekly_pipeline_status"] = _weekly_pipeline_likelihood(
        status,
        int(summary.get("validation_warning_count", 0)),
    )
    summary["run_weekly_pipeline_next"] = status == "Ready for weekly pipeline"
    summary["next_human_action"] = _next_action(
        status,
        template_created=bool(summary.get("template_created")),
        missing_books=int(summary.get("missing_book_count", 0)),
    )
    return _write_outputs(summary, attention, output_dir)


def run_week1_launch_readiness(
    fixtures_path: Path | None = None,
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    overwrite_template: bool = False,
    book: str = "",
    today: date | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Prepare and assess Week 1 inputs without inventing prices or running the model."""
    fixtures_path = fixtures_path or MANUAL_DIR / "upcoming_fixtures.csv"
    current_odds_path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    output_dir = output_dir or OUTPUTS_DIR
    today = today or date.today()
    summary = _base_summary(
        fixtures_path=fixtures_path,
        odds_path=current_odds_path,
        today=today,
        now=now,
    )
    attention: list[dict[str, object]] = []

    if not fixtures_path.exists():
        summary["fixture_status"] = "Missing"
        summary["fixture_note"] = "No upcoming fixtures file was found."
        summary["odds_file_status"] = (
            "Existing file preserved" if current_odds_path.exists() else "Not created without fixtures"
        )
        attention.append(
            _attention_row(
                category="Fixtures",
                severity="error",
                issue="missing_upcoming_fixtures",
                recommended_action="Add current Week 1 fixtures before creating an odds template.",
                details=f"Missing {fixtures_path}.",
            )
        )
        return _finish(summary, attention, output_dir, status="Missing fixtures")

    try:
        fixtures = pd.read_csv(fixtures_path, dtype=str).fillna("")
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        summary["fixture_status"] = "Unreadable"
        summary["fixture_note"] = f"Upcoming fixtures could not be read: {exc}"
        summary["odds_file_status"] = (
            "Existing file preserved" if current_odds_path.exists() else "Not created without readable fixtures"
        )
        attention.append(
            _attention_row(
                category="Fixtures",
                severity="error",
                issue="unreadable_upcoming_fixtures",
                recommended_action="Fix the fixture CSV, then rerun launch readiness.",
                details=summary["fixture_note"],
            )
        )
        return _finish(summary, attention, output_dir, status="Blocked")

    required_fixture_columns = {"date", "home_team", "away_team"}
    missing_fixture_columns = sorted(required_fixture_columns - set(fixtures.columns))
    if fixtures.empty or missing_fixture_columns:
        issue = "empty_upcoming_fixtures" if fixtures.empty else "missing_fixture_columns"
        detail = (
            "The upcoming fixtures file has no rows."
            if fixtures.empty
            else f"Missing required fixture column(s): {', '.join(missing_fixture_columns)}."
        )
        summary["fixture_status"] = "Needs refresh"
        summary["fixture_note"] = detail
        summary["odds_file_status"] = (
            "Existing file preserved" if current_odds_path.exists() else "Not created from invalid fixtures"
        )
        attention.append(
            _attention_row(
                category="Fixtures",
                severity="error",
                issue=issue,
                recommended_action="Replace the file with current Week 1 fixtures.",
                details=detail,
            )
        )
        return _finish(summary, attention, output_dir, status="Needs fixture refresh")

    fixture_freshness = inspect_fixture_date_freshness(fixtures_path, today=today)
    summary.update(
        {
            "fixture_status": _fixture_status_text(fixture_freshness),
            "fixture_note": fixture_freshness.note,
            "earliest_fixture_date": fixture_freshness.earliest_date,
            "latest_fixture_date": fixture_freshness.latest_date,
            "past_fixture_count": int(fixture_freshness.past_fixtures or 0),
            "invalid_fixture_date_count": int(fixture_freshness.invalid_fixture_dates or 0),
        }
    )
    if fixture_freshness.status != "Fresh":
        summary["odds_file_status"] = (
            "Existing file preserved" if current_odds_path.exists() else "Not created from stale/invalid fixtures"
        )
        attention.append(
            _attention_row(
                category="Fixtures",
                severity="error",
                issue="fixtures_not_fresh",
                recommended_action="Refresh or fix fixture dates before creating/filling Week 1 odds.",
                details=fixture_freshness.note,
            )
        )
        return _finish(summary, attention, output_dir, status="Needs fixture refresh")

    parsed_fixture_dates = pd.to_datetime(fixtures["date"], errors="coerce")
    future_mask = parsed_fixture_dates.dt.date >= today
    upcoming_fixtures = fixtures.loc[future_mask].copy()
    blank_team_mask = (
        upcoming_fixtures["home_team"].astype(str).str.strip().eq("")
        | upcoming_fixtures["away_team"].astype(str).str.strip().eq("")
    )
    summary["upcoming_fixture_count"] = int(len(upcoming_fixtures))
    week_column = next((column for column in ("matchweek", "week") if column in upcoming_fixtures.columns), None)
    summary["matchweek_column_available"] = bool(week_column)
    # Without a matchweek column the old fallback counted every upcoming fixture
    # as "Week 1", which reported a two-round slate as a single week. Fall back
    # to the reviewed date window instead.
    selected_fixtures = filter_to_selected_window(upcoming_fixtures, today=today)
    outside_fixtures = outside_selected_window(upcoming_fixtures, today=today)
    window_label = frame_window_label(upcoming_fixtures, today=today)
    summary["selected_window"] = window_label
    summary["selected_window_fixture_count"] = int(len(selected_fixtures))
    summary["fixtures_outside_selected_window_count"] = int(len(outside_fixtures))
    summary["fixtures_outside_selected_window"] = [
        f"{_clean(row.get('date'))}: {_clean(row.get('home_team'))} vs "
        f"{_clean(row.get('away_team'))}"
        for _, row in outside_fixtures.iterrows()
    ]
    summary["week1_fixture_count"] = (
        int(upcoming_fixtures[week_column].astype(str).str.strip().eq("1").sum())
        if week_column
        else int(len(selected_fixtures))
    )
    slate_warnings: list[str] = []
    if not week_column:
        slate_warnings.append(
            "`upcoming_fixtures.csv` has no matchweek column, so Week 1 is "
            f"determined by the reviewed date window ({window_label})."
        )
    if len(outside_fixtures):
        slate_warnings.append(
            f"{len(outside_fixtures)} upcoming fixture(s) fall outside the "
            f"selected Week 1 window ({window_label}). They belong to a "
            "later round and should not be treated as Week 1."
        )
    summary["slate_warnings"] = slate_warnings
    if upcoming_fixtures.empty or blank_team_mask.any():
        detail = (
            "No current/upcoming fixture rows remain after date filtering."
            if upcoming_fixtures.empty
            else f"{int(blank_team_mask.sum())} upcoming fixture row(s) have a blank team name."
        )
        summary["fixture_status"] = "Needs refresh"
        summary["fixture_note"] = detail
        summary["odds_file_status"] = (
            "Existing file preserved" if current_odds_path.exists() else "Not created from invalid fixtures"
        )
        attention.append(
            _attention_row(
                category="Fixtures",
                severity="error",
                issue="invalid_upcoming_fixture_rows",
                recommended_action="Fix the upcoming fixture rows before creating/filling odds.",
                details=detail,
            )
        )
        return _finish(summary, attention, output_dir, status="Needs fixture refresh")

    template_created = False
    template_overwritten = False
    if not current_odds_path.exists() or overwrite_template:
        try:
            _, template, _ = create_current_odds_template(
                upcoming_fixtures,
                current_odds_path,
                overwrite=overwrite_template,
                book=book,
            )
            if not template["american_odds"].fillna("").astype(str).str.strip().eq("").all():
                raise RuntimeError("The Week 1 template unexpectedly contained non-blank odds.")
        except FileExistsError as exc:
            summary["odds_file_status"] = "Existing file preserved after a safe creation stop"
            attention.append(
                _attention_row(
                    category="Odds fix",
                    severity="error",
                    issue="odds_file_appeared_during_setup",
                    recommended_action="Review the existing odds file, then rerun readiness.",
                    details=str(exc),
                )
            )
            return _finish(summary, attention, output_dir, status="Blocked")
        except (OSError, RuntimeError, ValueError) as exc:
            summary["odds_file_status"] = "Template creation failed safely"
            attention.append(
                _attention_row(
                    category="Odds fix",
                    severity="error",
                    issue="template_creation_failed",
                    recommended_action="Fix the file/path problem, then rerun readiness.",
                    details=f"The blank template could not be created safely: {exc}",
                )
            )
            return _finish(summary, attention, output_dir, status="Failed")
        template_created = True
        template_overwritten = bool(overwrite_template)
        summary["template_row_count"] = int(len(template))

    summary["template_created"] = template_created
    summary["template_overwritten"] = template_overwritten

    try:
        odds = pd.read_csv(current_odds_path, dtype=str).fillna("")
        odds_freshness = inspect_current_odds_date_freshness(current_odds_path, today=today)
        validation = build_current_odds_validation(
            current_odds_path,
            matches=pd.DataFrame(),
            fixtures=upcoming_fixtures,
        )
        completeness, completeness_summary = build_current_odds_completeness(
            current_odds_path,
            fixtures=upcoming_fixtures,
        )
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        summary["odds_file_status"] = f"Unreadable: {exc}"
        attention.append(
            _attention_row(
                category="Odds fix",
                severity="error",
                issue="unreadable_current_odds",
                recommended_action="Fix current_odds.csv, then rerun launch readiness.",
                details=f"Current odds could not be read: {exc}",
            )
        )
        return _finish(summary, attention, output_dir, status="Blocked")

    summary["odds_file_status"] = _odds_status_text(
        odds_freshness,
        template_created=template_created,
        template_overwritten=template_overwritten,
    )
    summary["current_odds_row_count"] = int(len(odds))
    summary["stale_odds_row_count"] = int(odds_freshness.past_rows or 0)
    summary["invalid_odds_date_row_count"] = int(odds_freshness.invalid_date_rows or 0)
    summary["earliest_odds_date"] = odds_freshness.earliest_date
    summary["latest_odds_date"] = odds_freshness.latest_date

    # Warn (never rewrite) when the odds template spans more than Week 1. The
    # file is protected: this reports the mismatch and leaves the fix to a human.
    odds_outside = (
        outside_selected_window(odds, today=today) if not odds.empty else odds.iloc[0:0]
    )
    summary["odds_rows_outside_selected_window_count"] = int(len(odds_outside))
    outside_matches = sorted(
        {
            f"{_clean(row.get('date'))}: {_clean(row.get('home_team'))} vs "
            f"{_clean(row.get('away_team'))}"
            for _, row in odds_outside.iterrows()
        }
    )
    summary["odds_matches_outside_selected_window"] = outside_matches
    if len(odds_outside):
        summary.setdefault("slate_warnings", []).append(
            f"`{current_odds_path.name}` contains {len(odds_outside)} row(s) "
            f"across {len(outside_matches)} match(es) outside the selected "
            f"Week 1 window ({window_label}). The file was not modified; "
            "trim or re-scope it deliberately before treating it as Week 1."
        )

    validation_csv = output_dir / "current_odds_validation.csv"
    validation_md = output_dir / "current_odds_validation.md"
    completeness_csv = output_dir / "current_odds_completeness.csv"
    completeness_md = output_dir / "current_odds_completeness.md"
    output_dir.mkdir(parents=True, exist_ok=True)
    validation.to_csv(validation_csv, index=False)
    validation_md.write_text(render_current_odds_validation_report(validation), encoding="utf-8")
    completeness.to_csv(completeness_csv, index=False)
    completeness_md.write_text(
        render_current_odds_completeness_report(completeness, completeness_summary),
        encoding="utf-8",
    )
    summary["validation_report_paths"] = {
        "csv": str(validation_csv),
        "markdown": str(validation_md),
    }
    summary["completeness_report_paths"] = {
        "csv": str(completeness_csv),
        "markdown": str(completeness_md),
    }

    serious = validation[validation["severity"] == "error"] if not validation.empty else pd.DataFrame(columns=VALIDATION_COLUMNS)
    warnings = validation[validation["severity"] != "error"] if not validation.empty else pd.DataFrame(columns=VALIDATION_COLUMNS)
    structural_errors = serious[~serious["issue"].isin(MISSING_ODDS_ISSUES)]
    missing_books = warnings[warnings["issue"] == "missing_book"]
    summary["invalid_odds_issue_count"] = int(len(structural_errors))
    summary["validation_warning_count"] = int(len(warnings))
    summary["missing_book_count"] = int(len(missing_books))
    summary["odds_completeness_percentage"] = float(
        completeness_summary.get("completion_percentage", 0.0)
    )
    summary["missing_odds_count"] = int(
        completeness_summary.get("rows_missing_odds", 0)
    ) + int(completeness_summary.get("missing_expected_rows", 0))

    for _, row in validation.iterrows():
        issue = _clean(row.get("issue"))
        if issue == "missing_american_odds":
            category = "Missing odds"
            action = "Enter a real sportsbook American price."
        elif issue == "missing_book":
            category = "Missing book"
            action = "Add the sportsbook name when known."
        elif issue in VALIDATION_DUPLICATES_FROM_COMPLETENESS:
            category = "Odds fix"
            action = "Fix this odds value or duplicate row before running the pipeline."
        elif _clean(row.get("severity")) == "error":
            category = "Odds fix"
            action = "Fix this matching or validation issue before running the pipeline."
        else:
            continue
        attention.append(
            _attention_row(
                category=category,
                severity=_clean(row.get("severity")),
                issue=issue,
                recommended_action=action,
                details=_clean(row.get("details")),
                source=row,
                current_value=row.get("american_odds", ""),
            )
        )

    missing_expected = completeness[
        completeness["issue"] == "missing_expected_market_row"
    ] if not completeness.empty else pd.DataFrame(columns=COMPLETENESS_COLUMNS)
    for _, row in missing_expected.iterrows():
        attention.append(
            _attention_row(
                category="Missing odds",
                severity="error",
                issue="missing_expected_market_row",
                recommended_action="Add this fixture/market row and enter a real sportsbook price.",
                details=_clean(row.get("details")),
                source=row,
            )
        )

    if "date" in odds.columns and not odds.empty:
        parsed_odds_dates = pd.to_datetime(odds["date"], errors="coerce")
        for index, row in odds.iterrows():
            row_with_number = row.copy()
            row_with_number["row_number"] = int(index) + 2
            raw_date = _clean(row.get("date"))
            parsed_date = parsed_odds_dates.loc[index]
            if pd.isna(parsed_date):
                attention.append(
                    _attention_row(
                        category="Odds date fix",
                        severity="error",
                        issue="blank_odds_date" if not raw_date else "invalid_odds_date",
                        recommended_action="Enter a valid match date before running the pipeline.",
                        details="The odds date is blank or malformed.",
                        source=row_with_number,
                        current_value=raw_date,
                    )
                )
            elif parsed_date.date() < today:
                attention.append(
                    _attention_row(
                        category="Stale odds",
                        severity="error",
                        issue="past_match_odds",
                        recommended_action="Remove/archive or replace this past-match odds row.",
                        details="This price is tied to a match before the launch-readiness date.",
                        source=row_with_number,
                        current_value=row.get("american_odds", ""),
                    )
                )

    has_structural_errors = bool(summary["invalid_odds_issue_count"])
    has_date_errors = bool(summary["invalid_odds_date_row_count"])
    has_stale_rows = bool(summary["stale_odds_row_count"])
    if has_structural_errors or has_date_errors or has_stale_rows:
        status = "Needs odds fixes"
    elif int(summary["missing_odds_count"]) or float(summary["odds_completeness_percentage"]) < 1.0:
        status = "Needs odds filled"
    else:
        status = "Ready for weekly pipeline"
    return _finish(summary, attention, output_dir, status=status)
