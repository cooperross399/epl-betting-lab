from __future__ import annotations

from datetime import date

import pandas as pd

from epl_betting_lab.reports.current_odds_import_audit import source_file_sha256
from epl_betting_lab.reports.stale_current_odds_archive import (
    CONFIRMATION_METADATA_FILENAME,
    archive_stale_current_odds,
)
from epl_betting_lab.reports.stale_current_odds_archive_confirmation import (
    STATUS_COLUMNS,
    build_stale_current_odds_archive_confirmation_status,
    save_stale_current_odds_archive_confirmation_status,
)


TODAY = date(2026, 7, 21)


def _write_odds(path) -> None:
    pd.DataFrame(
        [
            {
                "date": "2026-07-20",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "market": "1x2",
                "selection": "home",
                "american_odds": "-120",
                "book": "ExampleBook",
            },
            {
                "date": "2026-07-21",
                "home_team": "Liverpool",
                "away_team": "Everton",
                "market": "total_2_5",
                "selection": "over",
                "american_odds": "+105",
                "book": "ExampleBook",
            },
            {
                "date": "",
                "home_team": "Fulham",
                "away_team": "Brentford",
                "market": "btts",
                "selection": "yes",
                "american_odds": "-110",
                "book": "ExampleBook",
            },
        ]
    ).to_csv(path, index=False)


def _create_receipt(odds_path, output_dir) -> dict[str, object]:
    paths = archive_stale_current_odds(
        odds_path,
        output_dir,
        today=TODAY,
    )
    assert paths["status"] == "preview_ready"
    return paths


def test_ready_receipt_matches_current_odds_without_editing_them(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_odds(odds_path)
    preview_paths = _create_receipt(odds_path, output_dir)
    before = odds_path.read_bytes()

    report, summary = build_stale_current_odds_archive_confirmation_status(
        odds_path,
        preview_paths["metadata"],
        today=TODAY,
    )

    assert report.columns.tolist() == STATUS_COLUMNS
    assert len(report) == 1
    assert summary["status"] == "Ready"
    assert summary["confirm_id"] == preview_paths["confirm_id"]
    assert summary["receipt_created_at"]
    assert summary["preview_current_checksum_sha256"] == source_file_sha256(odds_path)
    assert summary["current_checksum_sha256"] == source_file_sha256(odds_path)
    assert summary["preview_stale_row_count"] == 1
    assert summary["current_stale_row_count"] == 1
    assert summary["preview_keep_row_count"] == 1
    assert summary["current_keep_row_count"] == 1
    assert summary["preview_manual_review_row_count"] == 1
    assert summary["current_manual_review_row_count"] == 1
    assert summary["exact_apply_command"].endswith(
        f"--confirm-id {preview_paths['confirm_id']}"
    )
    assert odds_path.read_bytes() == before
    assert not (odds_path.parent / "backups").exists()
    assert not (odds_path.parent / "archive").exists()


def test_save_writes_status_outputs_without_changing_odds_or_receipt(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_odds(odds_path)
    preview_paths = _create_receipt(odds_path, output_dir)
    odds_before = odds_path.read_bytes()
    receipt_before = preview_paths["metadata"].read_bytes()

    paths = save_stale_current_odds_archive_confirmation_status(
        odds_path,
        output_dir,
        today=TODAY,
    )

    assert paths["status"] == "Ready"
    assert paths["csv"].name == "stale_current_odds_archive_confirmation_status.csv"
    assert paths["markdown"].name == "stale_current_odds_archive_confirmation_status.md"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "This report only reads" in markdown
    assert paths["exact_apply_command"] in markdown
    assert odds_path.read_bytes() == odds_before
    assert preview_paths["metadata"].read_bytes() == receipt_before


def test_missing_receipt_has_beginner_friendly_status(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    _write_odds(odds_path)

    _, summary = build_stale_current_odds_archive_confirmation_status(
        odds_path,
        tmp_path / CONFIRMATION_METADATA_FILENAME,
        today=TODAY,
    )

    assert summary["status"] == "Missing receipt"
    assert summary["confirm_id"] == ""
    assert summary["exact_apply_command"] == ""
    assert summary["current_stale_row_count"] == 1
    assert summary["current_keep_row_count"] == 1
    assert summary["current_manual_review_row_count"] == 1
    assert "Run the stale odds archive preview" in summary["status_reason"]


def test_malformed_receipt_is_invalid(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    receipt_path = tmp_path / CONFIRMATION_METADATA_FILENAME
    _write_odds(odds_path)
    receipt_path.write_text("{not-json", encoding="utf-8")

    _, summary = build_stale_current_odds_archive_confirmation_status(
        odds_path,
        receipt_path,
        today=TODAY,
    )

    assert summary["status"] == "Invalid receipt"
    assert "malformed" in summary["status_reason"].lower()
    assert summary["exact_apply_command"] == ""


def test_changed_odds_invalidate_receipt(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_odds(odds_path)
    preview_paths = _create_receipt(odds_path, output_dir)
    odds = pd.read_csv(odds_path, dtype=str, keep_default_na=False)
    odds.loc[0, "american_odds"] = "-115"
    odds.to_csv(odds_path, index=False)

    _, summary = build_stale_current_odds_archive_confirmation_status(
        odds_path,
        preview_paths["metadata"],
        today=TODAY,
    )

    assert summary["status"] == "Odds changed after preview"
    assert (
        summary["preview_current_checksum_sha256"]
        != summary["current_checksum_sha256"]
    )
    assert summary["exact_apply_command"] == ""
    assert "Do not use the old confirmation ID" in summary["status_reason"]


def test_date_based_count_change_invalidates_receipt_without_file_change(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_odds(odds_path)
    preview_paths = _create_receipt(odds_path, output_dir)
    checksum = source_file_sha256(odds_path)

    _, summary = build_stale_current_odds_archive_confirmation_status(
        odds_path,
        preview_paths["metadata"],
        today=date(2026, 7, 22),
    )

    assert summary["status"] == "Odds changed after preview"
    assert summary["preview_current_checksum_sha256"] == checksum
    assert summary["current_checksum_sha256"] == checksum
    assert summary["preview_stale_row_count"] == 1
    assert summary["current_stale_row_count"] == 2
    assert "row counts no longer match" in summary["status_reason"]


def test_missing_current_odds_is_reported_for_existing_receipt(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_odds(odds_path)
    preview_paths = _create_receipt(odds_path, output_dir)
    odds_path.unlink()

    _, summary = build_stale_current_odds_archive_confirmation_status(
        odds_path,
        preview_paths["metadata"],
        today=TODAY,
    )

    assert summary["status"] == "Missing current_odds.csv"
    assert summary["current_checksum_sha256"] == ""
    assert summary["exact_apply_command"] == ""


def test_unreadable_current_odds_is_reported_for_existing_receipt(tmp_path) -> None:
    odds_path = tmp_path / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    _write_odds(odds_path)
    preview_paths = _create_receipt(odds_path, output_dir)
    odds_path.write_bytes(b"\xff\xfe\x00\x00")

    _, summary = build_stale_current_odds_archive_confirmation_status(
        odds_path,
        preview_paths["metadata"],
        today=TODAY,
    )

    assert summary["status"] == "Unreadable current_odds.csv"
    assert "could not be checked safely" in summary["status_reason"]
    assert summary["exact_apply_command"] == ""


def test_receipt_for_different_odds_path_is_invalid(tmp_path) -> None:
    preview_odds_path = tmp_path / "preview" / "current_odds.csv"
    current_odds_path = tmp_path / "current" / "current_odds.csv"
    output_dir = tmp_path / "outputs"
    preview_odds_path.parent.mkdir()
    current_odds_path.parent.mkdir()
    _write_odds(preview_odds_path)
    current_odds_path.write_bytes(preview_odds_path.read_bytes())
    preview_paths = _create_receipt(preview_odds_path, output_dir)

    _, summary = build_stale_current_odds_archive_confirmation_status(
        current_odds_path,
        preview_paths["metadata"],
        today=TODAY,
    )

    assert summary["status"] == "Invalid receipt"
    assert "different current_odds.csv path" in summary["status_reason"]
    assert summary["exact_apply_command"] == ""
