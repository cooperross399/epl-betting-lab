from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.thursday_best_bets_comparison import (
    build_thursday_best_bets_comparison,
    render_thursday_best_bets_comparison,
    save_thursday_best_bets_comparison,
)


def _write_archive(output_dir: Path, generated_at: str, rows: list[dict[str, object]]) -> Path:
    date_label = generated_at[:10]
    time_label = generated_at[11:19].replace(":", "")
    archive_dir = output_dir / "archive" / "thursday_best_bets" / date_label
    archive_dir.mkdir(parents=True, exist_ok=True)
    csv_path = archive_dir / f"{time_label}_thursday_best_bets.csv"
    metadata_path = archive_dir / f"{time_label}_thursday_best_bets_metadata.json"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    metadata_path.write_text(
        json.dumps({
            "generated_at": generated_at,
            "best_bets": 1,
            "leans": 0,
            "passes": 0,
            "validation_status": "ready",
            "csv": str(csv_path),
            "markdown": str(archive_dir / f"{time_label}_thursday_best_bets.md"),
        }),
        encoding="utf-8",
    )
    return csv_path


def _row(
    home_team: str,
    away_team: str,
    market: str,
    selection: str,
    status: str,
    tier: str,
    score: float,
    odds: int,
    edge: float,
    units: float,
) -> dict[str, object]:
    return {
        "home_team": home_team,
        "away_team": away_team,
        "market": market,
        "selection": selection,
        "status": status,
        "confidence_tier": tier,
        "ranking_score": score,
        "american_odds": odds,
        "calibrated_edge": edge,
        "suggested_units": units,
        "book": "FanDuel",
    }


def test_build_thursday_best_bets_comparison_finds_added_removed_and_changed_rows(tmp_path) -> None:
    previous_csv = _write_archive(
        tmp_path,
        "2026-07-08T12:00:00",
        [
            _row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -120, 0.03, 0.1),
            _row("Chelsea", "Fulham", "total_2_5", "under", "LEAN", "C", 45.0, 110, 0.04, 0.1),
        ],
    )
    latest_csv = _write_archive(
        tmp_path,
        "2026-07-09T12:00:00",
        [
            _row("Arsenal", "Coventry", "1x2", "home", "BETTABLE", "B", 65.0, -110, 0.05, 0.25),
            _row("Liverpool", "Leeds", "1x2", "home", "BETTABLE", "A", 82.0, 105, 0.12, 0.5),
        ],
    )

    comparison, summary = build_thursday_best_bets_comparison(tmp_path)

    assert summary["available"] is True
    assert summary["latest_archive"] == str(latest_csv)
    assert summary["previous_archive"] == str(previous_csv)
    assert set(comparison["change_type"]) == {"status_changed", "removed", "added"}
    arsenal = comparison[comparison["home_team"] == "Arsenal"].iloc[0]
    assert arsenal["previous_status"] == "LEAN"
    assert arsenal["latest_status"] == "BETTABLE"
    assert arsenal["ranking_score_change"] == 13.0
    assert arsenal["american_odds_change"] == 10.0
    assert arsenal["calibrated_edge_change"] == 0.02
    assert arsenal["suggested_units_change"] == 0.15

    markdown = render_thursday_best_bets_comparison(comparison, summary)
    assert "Plays Added" in markdown
    assert "Plays Removed" in markdown
    assert "Status Changes" in markdown


def test_save_thursday_best_bets_comparison_handles_missing_second_archive(tmp_path) -> None:
    _write_archive(
        tmp_path,
        "2026-07-09T12:00:00",
        [_row("Liverpool", "Leeds", "1x2", "home", "BETTABLE", "A", 82.0, 105, 0.12, 0.5)],
    )

    paths = save_thursday_best_bets_comparison(tmp_path)

    assert paths["csv"].name == "thursday_best_bets_comparison.csv"
    assert paths["markdown"].name == "thursday_best_bets_comparison.md"
    assert paths["csv"].exists()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "Comparison is not available yet" in markdown
    assert pd.read_csv(paths["csv"]).empty
