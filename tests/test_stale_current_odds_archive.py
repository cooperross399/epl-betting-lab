from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import epl_betting_lab.reports.stale_current_odds_archive as archive_module
from epl_betting_lab.reports.stale_current_odds_archive import (
    AUDIT_COLUMNS,
    PREVIEW_COLUMNS,
    archive_stale_current_odds,
    build_stale_current_odds_archive_preview,
)


TODAY = date(2026, 7, 21)
TIMESTAMP = "2026-07-21_110000"


def _write_mixed_odds(path) -> None:
    pd.DataFrame(
        [
            {
                "date": "2026-07-20",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "market": "1x2",
                "selection": "home",
                "american_odds": "-120",
                "closing_american_odds": "-125",
                "book": "ExampleBook",
                "notes": "archive this stale row",
                "custom_column": "stale-extra",
            },
            {
                "date": "2026-07-21",
                "home_team": "Liverpool",
                "away_team": "Everton",
                "market": "total_2_5",
                "selection": "over",
                "american_odds": "+105",
                "closing_american_odds": "",
                "book": "ExampleBook",
                "notes": "keep today",
                "custom_column": "today-extra",
            },
            {
                "date": "2026-08-01",
                "home_team": "Fulham",
                "away_team": "Brentford",
                "market": "btts",
                "selection": "yes",
                "american_odds": "-110",
                "closing_american_odds": "",
                "book": "ExampleBook",
                "notes": "keep future",
                "custom_column": "future-extra",
            },
            {
                "date": "not-a-date",
                "home_team": "Leeds",
                "away_team": "Burnley",
                "market": "1x2",
                "selection": "draw",
                "american_odds": "+220",
                "closing_american_odds": "",
                "book": "ExampleBook",
                "notes": "fix this date",
                "custom_column": "invalid-extra",
            },
            {
                "date": "",
                "home_team": "Sunderland",
                "away_team": "Bournemouth",
                "market": "total_2_5",
                "selection": "under",
                "american_odds": "+115",
                "closing_american_odds": "",
                "book": "ExampleBook",
                "notes": "fill this date",
                "custom_column": "blank-extra",
            },
        ]
    ).to_csv(path, index=False)


def test_preview_classifies_archive_keep_and_manual_review_rows(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    _write_mixed_odds(odds_path)

    preview, summary = build_stale_current_odds_archive_preview(odds_path, today=TODAY)

    assert preview.columns.tolist() == PREVIEW_COLUMNS
    assert preview["archive_action"].tolist() == [
        "Archive and remove",
        "Keep",
        "Keep",
        "Keep for manual review",
        "Keep for manual review",
    ]
    assert summary["status"] == "preview_ready"
    assert summary["stale_rows"] == 1
    assert summary["current_rows"] == 2
    assert summary["invalid_date_rows"] == 1
    assert summary["blank_date_rows"] == 1
    assert summary["rows_kept"] == 4


def test_preview_writes_reports_without_changing_or_archiving_odds(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()

    paths = archive_stale_current_odds(odds_path, output_dir, today=TODAY)

    assert paths["status"] == "preview_ready"
    assert paths["csv"].name == "stale_current_odds_archive_preview.csv"
    assert paths["markdown"].name == "stale_current_odds_archive_preview.md"
    assert odds_path.read_bytes() == before
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Preview only: no input files were changed" in markdown
    assert "Rows To Archive And Remove" in markdown


def test_apply_backs_up_archives_and_keeps_current_and_date_fix_rows(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()
    before_frame = pd.read_csv(odds_path, dtype=str, keep_default_na=False)

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        today=TODAY,
        timestamp=TIMESTAMP,
        archive_id="stale-archive-test",
        applied_at="2026-07-21T11:00:00-04:00",
    )

    assert paths["status"] == "applied"
    assert paths["backup"].read_bytes() == before
    archived = pd.read_csv(paths["stale_archive"], dtype=str, keep_default_na=False)
    current = pd.read_csv(odds_path, dtype=str, keep_default_na=False)
    assert archived.columns.tolist() == before_frame.columns.tolist()
    assert archived["custom_column"].tolist() == ["stale-extra"]
    assert current["custom_column"].tolist() == [
        "today-extra",
        "future-extra",
        "invalid-extra",
        "blank-extra",
    ]
    assert current["date"].tolist() == ["2026-07-21", "2026-08-01", "not-a-date", ""]
    audit = pd.read_csv(paths["audit_csv"], dtype=str, keep_default_na=False)
    assert audit.columns.tolist() == AUDIT_COLUMNS
    assert audit.iloc[-1]["archive_id"] == "stale-archive-test"
    assert audit.iloc[-1]["stale_rows_archived"] == "1"
    assert audit.iloc[-1]["current_rows_kept"] == "2"
    assert audit.iloc[-1]["date_fix_rows_kept"] == "2"
    assert audit.iloc[-1]["rows_after"] == "4"
    assert "Preview only" in paths["markdown"].read_text(encoding="utf-8")
    assert "Latest Apply" in paths["audit_markdown"].read_text(encoding="utf-8")


def test_apply_with_no_stale_rows_is_a_read_only_no_op(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame(
        [
            {"date": "2026-07-21", "home_team": "Arsenal", "away_team": "Chelsea"},
            {"date": "not-a-date", "home_team": "Leeds", "away_team": "Burnley"},
        ]
    ).to_csv(odds_path, index=False)
    before = odds_path.read_bytes()

    paths = archive_stale_current_odds(odds_path, output_dir, apply=True, today=TODAY)

    assert paths["status"] == "no_stale_rows"
    assert odds_path.read_bytes() == before
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()
    assert "Date Rows Kept For Manual Fixing" in paths["markdown"].read_text(encoding="utf-8")


def test_apply_all_stale_rows_leaves_a_header_only_current_odds_file(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    pd.DataFrame(
        [
            {"date": "2026-07-01", "home_team": "Arsenal", "away_team": "Chelsea"},
            {"date": "2026-07-02", "home_team": "Leeds", "away_team": "Burnley"},
        ]
    ).to_csv(odds_path, index=False)

    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        apply=True,
        today=TODAY,
        timestamp=TIMESTAMP,
    )

    current = pd.read_csv(odds_path, dtype=str, keep_default_na=False)
    archived = pd.read_csv(paths["stale_archive"], dtype=str, keep_default_na=False)
    assert current.empty
    assert current.columns.tolist() == ["date", "home_team", "away_team"]
    assert len(archived) == 2


@pytest.mark.parametrize(
    ("setup", "expected_status"),
    [
        ("missing", "missing_file"),
        ("empty", "empty_file"),
        ("missing_date", "missing_date_column"),
        ("unreadable", "unreadable_file"),
    ],
)
def test_apply_refuses_invalid_source_files(tmp_path, setup, expected_status) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    if setup == "empty":
        odds_path.write_text("", encoding="utf-8")
    elif setup == "missing_date":
        pd.DataFrame([{"home_team": "Arsenal", "away_team": "Chelsea"}]).to_csv(
            odds_path,
            index=False,
        )
    elif setup == "unreadable":
        odds_path.write_bytes(b"\xff\xfe\x00\x00")
    before = odds_path.read_bytes() if odds_path.exists() else None

    paths = archive_stale_current_odds(odds_path, output_dir, apply=True, today=TODAY)

    assert paths["status"] == expected_status
    assert (odds_path.read_bytes() if odds_path.exists() else None) == before
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()
    assert "no input files were changed" in paths["markdown"].read_text(encoding="utf-8").lower()


def test_apply_refuses_backup_or_archive_collision(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()
    backup_dir = odds_path.parent / "backups"
    backup_dir.mkdir()
    collision = backup_dir / f"{TIMESTAMP}_current_odds_pre_stale_archive.csv"
    collision.write_text("existing backup", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        archive_stale_current_odds(
            odds_path,
            output_dir,
            apply=True,
            today=TODAY,
            timestamp=TIMESTAMP,
        )

    assert odds_path.read_bytes() == before
    assert collision.read_text(encoding="utf-8") == "existing backup"
    assert not (odds_path.parent / "archive" / "current_odds_stale").exists()


def test_apply_refuses_to_overwrite_unreadable_existing_audit(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()
    audit_path = output_dir / "stale_current_odds_archive_audit.csv"
    audit_path.write_text("wrong,column\n", encoding="utf-8")

    with pytest.raises(ValueError, match="audit"):
        archive_stale_current_odds(
            odds_path,
            output_dir,
            apply=True,
            today=TODAY,
            timestamp=TIMESTAMP,
        )

    assert odds_path.read_bytes() == before
    assert audit_path.read_text(encoding="utf-8") == "wrong,column\n"
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()


def test_current_odds_stays_unchanged_if_atomic_rewrite_fails(tmp_path, monkeypatch) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_mixed_odds(odds_path)
    before = odds_path.read_bytes()
    real_write = archive_module._write_csv_atomic

    def fail_current_write(frame, path, *, overwrite=True):
        if path == odds_path:
            raise OSError("simulated current odds write failure")
        return real_write(frame, path, overwrite=overwrite)

    monkeypatch.setattr(archive_module, "_write_csv_atomic", fail_current_write)

    with pytest.raises(OSError, match="simulated"):
        archive_stale_current_odds(
            odds_path,
            output_dir,
            apply=True,
            today=TODAY,
            timestamp=TIMESTAMP,
        )

    assert odds_path.read_bytes() == before
    backup_path = odds_path.parent / "backups" / f"{TIMESTAMP}_current_odds_pre_stale_archive.csv"
    stale_path = (
        odds_path.parent
        / "archive"
        / "current_odds_stale"
        / f"{TIMESTAMP}_current_odds_stale.csv"
    )
    assert backup_path.exists()
    assert stale_path.exists()
    assert not (output_dir / "stale_current_odds_archive_audit.csv").exists()
