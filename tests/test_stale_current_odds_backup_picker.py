from __future__ import annotations

from datetime import date

import pandas as pd

from epl_betting_lab.reports.stale_current_odds_backup_picker import (
    BACKUP_LIST_COLUMNS,
    build_stale_current_odds_backup_list,
    save_stale_current_odds_backup_list,
)


TODAY = date(2026, 7, 21)


def _write_odds(path, dates: list[str]) -> None:
    pd.DataFrame(
        [
            {
                "date": match_date,
                "home_team": f"Home {position}",
                "away_team": f"Away {position}",
                "market": "1x2",
                "selection": "home",
                "american_odds": "-110",
                "book": "ExampleBook",
            }
            for position, match_date in enumerate(dates, start=1)
        ]
    ).to_csv(path, index=False)


def test_backup_list_finds_archive_and_rollback_backups_with_date_details(tmp_path) -> None:
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()
    archive_backup = backups_dir / "2026-07-21_110000_current_odds_pre_stale_archive.csv"
    rollback_backup = (
        backups_dir
        / "2026-07-22_090000_123456_current_odds_pre_stale_archive_rollback.csv"
    )
    malformed_name = backups_dir / "mystery_current_odds_pre_stale_archive.csv"
    _write_odds(archive_backup, ["2026-07-20", "2026-08-01", "not-a-date", ""])
    _write_odds(rollback_backup, ["2026-08-02"])
    _write_odds(malformed_name, ["2026-08-03"])
    _write_odds(backups_dir / "unrelated.csv", ["2026-08-04"])

    backup_list, summary = build_stale_current_odds_backup_list(
        backups_dir,
        today=TODAY,
    )

    assert backup_list.columns.tolist() == BACKUP_LIST_COLUMNS
    assert len(backup_list) == 3
    assert summary["status"] == "ready"
    assert summary["backups_found"] == 3
    assert summary["valid_backups"] == 3
    assert summary["malformed_filename_count"] == 1
    assert not backup_list["backup_path"].str.endswith("unrelated.csv").any()

    archive = backup_list.loc[backup_list["backup_path"] == str(archive_backup)].iloc[0]
    assert archive["backup_type"] == "Pre-archive"
    assert archive["filename_timestamp"].startswith("2026-07-21")
    assert archive["filename_status"] == "Parsed"
    assert archive["file_modified_at"]
    assert archive["row_count"] == 4
    assert archive["earliest_odds_date"] == "2026-07-20"
    assert archive["latest_odds_date"] == "2026-08-01"
    assert archive["stale_rows"] == 1
    assert archive["current_rows"] == 1
    assert archive["invalid_date_rows"] == 1
    assert archive["blank_date_rows"] == 1
    assert archive["readable"] == "Yes"
    assert archive["valid"] == "Yes"

    recovery = backup_list.loc[backup_list["backup_path"] == str(rollback_backup)].iloc[0]
    assert recovery["backup_type"] == "Pre-rollback recovery"
    assert recovery["filename_status"] == "Parsed"
    assert recovery["current_rows"] == 1

    malformed = backup_list.loc[backup_list["backup_path"] == str(malformed_name)].iloc[0]
    assert malformed["filename_timestamp"] == ""
    assert malformed["filename_status"] == "Malformed filename timestamp"
    assert malformed["valid"] == "Yes"
    assert "modified time" in malformed["message"]


def test_backup_list_keeps_invalid_files_visible_with_beginner_statuses(tmp_path) -> None:
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()
    malformed_csv = backups_dir / "2026-07-21_100000_current_odds_pre_stale_archive.csv"
    unreadable = backups_dir / "2026-07-21_100001_current_odds_pre_stale_archive.csv"
    empty = backups_dir / "2026-07-21_100002_current_odds_pre_stale_archive.csv"
    header_only = backups_dir / "2026-07-21_100003_current_odds_pre_stale_archive.csv"
    missing_date = backups_dir / "2026-07-21_100004_current_odds_pre_stale_archive.csv"
    malformed_csv.write_text('date,home_team\n"2026-07-20,Arsenal\n', encoding="utf-8")
    unreadable.write_bytes(b"\xff\xfe\x00\x00")
    empty.write_text("", encoding="utf-8")
    header_only.write_text("date,home_team,away_team\n", encoding="utf-8")
    pd.DataFrame([{"home_team": "Arsenal", "away_team": "Chelsea"}]).to_csv(
        missing_date,
        index=False,
    )

    backup_list, summary = build_stale_current_odds_backup_list(
        backups_dir,
        today=TODAY,
    )

    statuses = dict(zip(backup_list["backup_path"], backup_list["status"]))
    assert statuses[str(malformed_csv)] == "Malformed CSV"
    assert statuses[str(unreadable)] == "Unreadable backup"
    assert statuses[str(empty)] == "Empty backup"
    assert statuses[str(header_only)] == "Empty backup"
    assert statuses[str(missing_date)] == "Missing date column"
    assert backup_list["valid"].eq("No").all()
    assert summary["status"] == "needs_review"
    assert summary["invalid_backups"] == 5


def test_no_backups_writes_friendly_empty_reports_without_creating_backup_folder(tmp_path) -> None:
    backups_dir = tmp_path / "missing_backups"
    output_dir = tmp_path / "outputs"

    paths = save_stale_current_odds_backup_list(
        backups_dir,
        output_dir,
        today=TODAY,
    )

    assert paths["status"] == "no_backups"
    assert paths["csv"].name == "stale_current_odds_backup_list.csv"
    assert paths["markdown"].name == "stale_current_odds_backup_list.md"
    report = pd.read_csv(paths["csv"], dtype=str, keep_default_na=False)
    assert report.empty
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "No backups found" in markdown
    assert "Do not apply an archive just to create a backup" in markdown
    assert not backups_dir.exists()


def test_saving_backup_list_never_changes_backup_files(tmp_path) -> None:
    backups_dir = tmp_path / "backups"
    backups_dir.mkdir()
    backup_path = backups_dir / "2026-07-21_110000_current_odds_pre_stale_archive.csv"
    output_dir = tmp_path / "outputs"
    _write_odds(backup_path, ["2026-07-20", "2026-08-01"])
    before = backup_path.read_bytes()
    modified_before = backup_path.stat().st_mtime_ns

    paths = save_stale_current_odds_backup_list(
        backups_dir,
        output_dir,
        today=TODAY,
    )

    assert paths["status"] == "ready"
    assert backup_path.read_bytes() == before
    assert backup_path.stat().st_mtime_ns == modified_before
    assert not (output_dir / "stale_current_odds_archive_rollback_audit.csv").exists()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Read-only report" in markdown
    assert "valid = Yes" in markdown
