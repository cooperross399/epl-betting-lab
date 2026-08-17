from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.fixture_slate_trim import (
    TRIM_AUDIT_CSV_FILENAME,
    TRIM_PREVIEW_CSV_FILENAME,
    TRIM_PREVIEW_JSON_FILENAME,
    TRIM_PREVIEW_MARKDOWN_FILENAME,
    apply_fixture_slate_trim,
    build_fixture_slate_trim_preview,
    save_fixture_slate_trim_preview,
)


TODAY = date(2026, 8, 17)
NOW = datetime(2026, 8, 17, 12, 0, 0)


def _write_slate(tmp_path: Path, rows: list[str]) -> Path:
    manual = tmp_path / "manual"
    manual.mkdir(parents=True, exist_ok=True)
    path = manual / "upcoming_fixtures.csv"
    path.write_text(
        "date,home_team,away_team,notes\n" + "\n".join(rows) + "\n", encoding="utf-8"
    )
    return path


def _two_week_slate(tmp_path: Path) -> Path:
    return _write_slate(
        tmp_path,
        [
            "2026-08-21,Arsenal,Coventry,opening note",
            "2026-08-22,Everton,Crystal Palace,",
            "2026-08-28,Coventry,Hull,later matchweek",
            "2026-08-29,Liverpool,Nott'm Forest,",
        ],
    )


def test_preview_splits_imminent_and_later_matchweeks(tmp_path: Path) -> None:
    fixtures = _two_week_slate(tmp_path)

    preview = build_fixture_slate_trim_preview(fixtures, today=TODAY)

    assert preview["status"] == "Trim preview ready"
    assert preview["kept_count"] == 2
    assert preview["deferred_count"] == 2
    assert preview["attention_count"] == 0
    assert preview["matchweek_group_count"] == 2
    assert preview["confirm_id"]
    decisions = list(preview["rows"]["trim_decision"])
    assert decisions[0].startswith("Keep")
    assert decisions[2].startswith("Defer")


def test_single_matchweek_slate_has_nothing_to_defer(tmp_path: Path) -> None:
    fixtures = _write_slate(
        tmp_path,
        ["2026-08-21,Arsenal,Coventry,", "2026-08-22,Everton,Crystal Palace,"],
    )

    preview = build_fixture_slate_trim_preview(fixtures, today=TODAY)

    assert preview["status"] == "Nothing to defer"
    assert preview["confirm_id"] == ""


def test_past_and_invalid_dates_are_kept_for_manual_attention(tmp_path: Path) -> None:
    fixtures = _write_slate(
        tmp_path,
        [
            "2026-08-01,Old,Match,",
            "bad-date,Broken,Row,",
            "2026-08-21,Arsenal,Coventry,",
            "2026-08-29,Liverpool,Everton,",
        ],
    )

    preview = build_fixture_slate_trim_preview(fixtures, today=TODAY)

    assert preview["status"] == "Trim preview ready"
    assert preview["attention_count"] == 2
    assert preview["kept_count"] == 1
    assert preview["deferred_count"] == 1


def test_missing_slate_is_reported(tmp_path: Path) -> None:
    preview = build_fixture_slate_trim_preview(
        tmp_path / "missing.csv", today=TODAY
    )

    assert preview["status"] == "Missing fixtures"
    assert preview["confirm_id"] == ""


def test_all_past_slate_needs_refresh_not_trim(tmp_path: Path) -> None:
    fixtures = _write_slate(tmp_path, ["2026-08-01,Old,Match,"])

    preview = build_fixture_slate_trim_preview(fixtures, today=TODAY)

    assert preview["status"] == "Needs fixture refresh"


def test_preview_writes_reports_and_edits_nothing(tmp_path: Path) -> None:
    fixtures = _two_week_slate(tmp_path)
    before = fixtures.read_bytes()
    output_dir = tmp_path / "outputs"

    preview = build_fixture_slate_trim_preview(fixtures, today=TODAY)
    paths = save_fixture_slate_trim_preview(preview, output_dir)

    for filename in (
        TRIM_PREVIEW_JSON_FILENAME,
        TRIM_PREVIEW_MARKDOWN_FILENAME,
        TRIM_PREVIEW_CSV_FILENAME,
    ):
        assert (output_dir / filename).exists()
    assert fixtures.read_bytes() == before
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert preview["confirm_id"] in markdown


def test_apply_with_valid_confirm_id_trims_backs_up_and_archives(tmp_path: Path) -> None:
    fixtures = _two_week_slate(tmp_path)
    output_dir = tmp_path / "outputs"
    preview = build_fixture_slate_trim_preview(fixtures, today=TODAY)

    result = apply_fixture_slate_trim(
        fixtures,
        confirm_id=preview["confirm_id"],
        output_dir=output_dir,
        today=TODAY,
        now=NOW,
    )

    assert result["status"] == "Trim applied"
    trimmed = pd.read_csv(fixtures, dtype=str, keep_default_na=False)
    assert len(trimmed) == 2
    assert list(trimmed.columns) == ["date", "home_team", "away_team", "notes"]
    assert trimmed.iloc[0]["notes"] == "opening note"
    backup = pd.read_csv(result["backup_path"], dtype=str, keep_default_na=False)
    assert len(backup) == 4
    deferred = pd.read_csv(
        result["deferred_archive_path"], dtype=str, keep_default_na=False
    )
    assert len(deferred) == 2
    assert set(deferred["home_team"]) == {"Coventry", "Liverpool"}
    assert (output_dir / TRIM_AUDIT_CSV_FILENAME).exists()


def test_apply_with_wrong_confirm_id_is_blocked(tmp_path: Path) -> None:
    fixtures = _two_week_slate(tmp_path)
    before = fixtures.read_bytes()

    result = apply_fixture_slate_trim(
        fixtures,
        confirm_id="not-the-right-id",
        output_dir=tmp_path / "outputs",
        today=TODAY,
        now=NOW,
    )

    assert result["status"] == "Blocked"
    assert fixtures.read_bytes() == before
    assert "confirmation ID" in result["message"]


def test_apply_is_blocked_when_file_changed_after_preview(tmp_path: Path) -> None:
    fixtures = _two_week_slate(tmp_path)
    preview = build_fixture_slate_trim_preview(fixtures, today=TODAY)
    fixtures.write_text(
        fixtures.read_text(encoding="utf-8") + "2026-08-30,Extra,Fixture,\n",
        encoding="utf-8",
    )
    before = fixtures.read_bytes()

    result = apply_fixture_slate_trim(
        fixtures,
        confirm_id=preview["confirm_id"],
        output_dir=tmp_path / "outputs",
        today=TODAY,
        now=NOW,
    )

    assert result["status"] == "Blocked"
    assert fixtures.read_bytes() == before


def test_apply_on_single_matchweek_slate_is_blocked_safely(tmp_path: Path) -> None:
    fixtures = _write_slate(tmp_path, ["2026-08-21,Arsenal,Coventry,"])

    result = apply_fixture_slate_trim(
        fixtures,
        confirm_id="anything",
        output_dir=tmp_path / "outputs",
        today=TODAY,
        now=NOW,
    )

    assert result["status"] == "Blocked"
    assert "Nothing to defer" in result["message"]
