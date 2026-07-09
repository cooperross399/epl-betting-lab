from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.thursday_archive_pair import (
    build_thursday_archive_history_details,
    build_thursday_archive_pair,
    list_thursday_archive_snapshots,
)


def _write_archive(output_dir: Path, generated_at: str, with_metadata: bool = True) -> Path:
    archive_dir = output_dir / "archive" / "thursday_best_bets" / generated_at[:10]
    archive_dir.mkdir(parents=True, exist_ok=True)
    time_label = generated_at[11:19].replace(":", "")
    csv_path = archive_dir / f"{time_label}_thursday_best_bets.csv"
    pd.DataFrame([{"home_team": "Arsenal", "away_team": "Coventry"}]).to_csv(csv_path, index=False)
    if with_metadata:
        metadata_path = archive_dir / f"{time_label}_thursday_best_bets_metadata.json"
        metadata_path.write_text(
            json.dumps({
                "generated_at": generated_at,
                "validation_status": "ready",
                "best_bets": 1,
                "leans": 2,
                "passes": 3,
                "csv": str(csv_path),
                "markdown": str(archive_dir / f"{time_label}_thursday_best_bets.md"),
            }),
            encoding="utf-8",
        )
    return csv_path


def test_archive_pair_reports_no_archives(tmp_path) -> None:
    pair = build_thursday_archive_pair(tmp_path)

    assert pair["available"] is False
    assert pair["status"] == "no_archives"
    assert pair["label"] == "No archived snapshots found"


def test_archive_pair_reports_one_archive(tmp_path) -> None:
    _write_archive(tmp_path, "2026-07-09T12:30:00")

    pair = build_thursday_archive_pair(tmp_path)

    assert pair["available"] is False
    assert pair["status"] == "one_archive"
    assert pair["label"] == "Only one archived snapshot found: 2026-07-09 12:30:00"


def test_archive_pair_uses_metadata_labels_for_latest_two(tmp_path) -> None:
    _write_archive(tmp_path, "2026-07-08T11:00:00")
    latest_csv = _write_archive(tmp_path, "2026-07-09T12:30:00")

    pair = build_thursday_archive_pair(tmp_path)

    assert pair["available"] is True
    assert pair["status"] == "ready"
    assert pair["label"] == "Comparing: 2026-07-09 12:30:00 vs 2026-07-08 11:00:00"
    assert pair["latest"]["csv"] == str(latest_csv)
    assert pair["latest"]["source"] == "metadata"


def test_archive_snapshots_fall_back_to_csv_filename_without_metadata(tmp_path) -> None:
    _write_archive(tmp_path, "2026-07-08T11:00:00", with_metadata=False)
    _write_archive(tmp_path, "2026-07-09T12:30:00", with_metadata=False)

    snapshots = list_thursday_archive_snapshots(tmp_path)
    pair = build_thursday_archive_pair(tmp_path)

    assert list(snapshots["source"]) == ["csv_filename", "csv_filename"]
    assert pair["label"] == "Comparing: 2026-07-09 12:30:00 vs 2026-07-08 11:00:00"


def test_archive_history_details_use_metadata_counts(tmp_path) -> None:
    _write_archive(tmp_path, "2026-07-08T11:00:00")
    _write_archive(tmp_path, "2026-07-09T12:30:00")

    details, message = build_thursday_archive_history_details(tmp_path)

    assert message == ""
    assert list(details["snapshot"]) == ["Latest", "Previous"]
    assert details.iloc[0]["archive_label"] == "2026-07-09 12:30:00"
    assert details.iloc[0]["validation_status"] == "ready"
    assert details.iloc[0]["best_bets"] == 1
    assert details.iloc[0]["leans"] == 2
    assert details.iloc[0]["passes"] == 3
    assert details.iloc[0]["total_rows"] == 1
    assert details.iloc[0]["metadata"]


def test_archive_history_details_fall_back_to_csv_without_metadata(tmp_path) -> None:
    archive_dir = tmp_path / "archive" / "thursday_best_bets" / "2026-07-09"
    archive_dir.mkdir(parents=True, exist_ok=True)
    csv_path = archive_dir / "123000_thursday_best_bets.csv"
    pd.DataFrame([
        {"section": "Best bets"},
        {"section": "Leans"},
        {"section": "Passes / notable avoids"},
    ]).to_csv(csv_path, index=False)

    details, _ = build_thursday_archive_history_details(tmp_path)

    assert details.iloc[0]["best_bets"] == 1
    assert details.iloc[0]["leans"] == 1
    assert details.iloc[0]["passes"] == 1
    assert details.iloc[0]["total_rows"] == 3
    assert "Metadata JSON missing" in details.iloc[0]["notes"]


def test_archive_history_details_handles_unreadable_csv(tmp_path) -> None:
    archive_dir = tmp_path / "archive" / "thursday_best_bets" / "2026-07-09"
    archive_dir.mkdir(parents=True, exist_ok=True)
    csv_path = archive_dir / "123000_thursday_best_bets.csv"
    csv_path.write_text('bad,csv\n"unterminated\n', encoding="utf-8")

    details, _ = build_thursday_archive_history_details(tmp_path)

    assert details.iloc[0]["total_rows"] == ""
    assert "Could not read archived CSV" in details.iloc[0]["notes"]


def test_archive_history_details_reports_no_or_one_archive(tmp_path) -> None:
    empty_details, empty_message = build_thursday_archive_history_details(tmp_path)
    assert empty_details.empty
    assert empty_message == "No archived snapshots found yet."

    _write_archive(tmp_path, "2026-07-09T12:30:00")
    one_detail, one_message = build_thursday_archive_history_details(tmp_path)
    assert len(one_detail) == 1
    assert "Only one archived snapshot found" in one_message
