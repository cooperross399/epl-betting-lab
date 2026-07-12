from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.thursday_best_bets_comparison import (
    build_recommended_next_action,
    build_thursday_best_bets_comparison,
    build_top_card_movement_reason,
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
    assert summary["comparison_label"] == "Comparing: 2026-07-09 12:00:00 vs 2026-07-08 12:00:00"
    assert set(comparison["change_type"]) == {"status_changed", "removed", "added"}
    arsenal = comparison[comparison["home_team"] == "Arsenal"].iloc[0]
    assert arsenal["movement_category"] == "Became BETTABLE"
    assert arsenal["importance_score"] == 100.0
    assert "BETTABLE" in arsenal["movement_reason"]
    assert arsenal["action_needed"] == "Review price"
    assert "price" in arsenal["action_reason"]
    assert arsenal["previous_status"] == "LEAN"
    assert arsenal["latest_status"] == "BETTABLE"
    assert arsenal["ranking_score_change"] == 13.0
    assert arsenal["american_odds_change"] == 10.0
    assert arsenal["calibrated_edge_change"] == 0.02
    assert arsenal["suggested_units_change"] == 0.15

    markdown = render_thursday_best_bets_comparison(comparison, summary)
    assert "Comparing: 2026-07-09 12:00:00 vs 2026-07-08 12:00:00" in markdown
    assert "Card count changes: Best bets 1 -> 1 (0), Leans 0 -> 0 (0), Passes 0 -> 0 (0), Total 1 -> 1 (0)" in markdown
    assert "Count-change risk: Stable card" in markdown
    assert "Top card movement reason: Mostly new/removed plays" in markdown
    assert "Recommended next action: Review removals first" in markdown
    assert "Action needed" in markdown
    assert "Biggest changes" in markdown
    assert "Became BETTABLE" in markdown
    assert "Action: Review price" in markdown
    assert "Plays Added" in markdown
    assert "Plays Removed" in markdown
    assert "Status Changes" in markdown


def test_movement_summary_highlights_downgrades_and_lost_edges(tmp_path) -> None:
    _write_archive(
        tmp_path,
        "2026-07-08T12:00:00",
        [
            _row("Spurs", "Wolves", "1x2", "home", "BETTABLE", "A", 78.0, -130, 0.08, 0.5),
            _row("Chelsea", "Fulham", "total_2_5", "under", "LEAN", "C", 43.0, 120, 0.03, 0.1),
        ],
    )
    _write_archive(
        tmp_path,
        "2026-07-09T12:00:00",
        [
            _row("Spurs", "Wolves", "1x2", "home", "PASS - too much juice", "Pass/Avoid", 25.0, -180, -0.01, 0.0),
            _row("Chelsea", "Fulham", "total_2_5", "under", "LEAN", "C", 47.0, 135, 0.05, 0.1),
        ],
    )

    comparison, _ = build_thursday_best_bets_comparison(tmp_path)

    spurs = comparison[comparison["home_team"] == "Spurs"].iloc[0]
    chelsea = comparison[comparison["home_team"] == "Chelsea"].iloc[0]
    assert spurs["movement_category"] == "Became PASS/Avoid"
    assert spurs["action_needed"] == "Likely remove from card"
    assert spurs["importance_score"] > chelsea["importance_score"]
    assert chelsea["movement_category"] == "Edge improved"
    assert chelsea["action_needed"] == "Candidate upgrade"
    assert {"movement_category", "importance_score", "movement_reason", "action_needed", "action_reason"}.issubset(
        comparison.columns
    )


def test_action_needed_flags_odds_recheck_without_edge_improvement(tmp_path) -> None:
    _write_archive(
        tmp_path,
        "2026-07-08T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -120, 0.03, 0.1)],
    )
    _write_archive(
        tmp_path,
        "2026-07-09T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -105, 0.03, 0.1)],
    )

    comparison, _ = build_thursday_best_bets_comparison(tmp_path)

    row = comparison.iloc[0]
    assert row["movement_category"] == "Odds moved in our favor"
    assert row["action_needed"] == "Recheck odds"


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
    assert "Only one archived snapshot found: 2026-07-09 12:00:00" in markdown
    assert "Card count changes: only one archived snapshot found." in markdown
    assert "Count-change risk: Not enough archive history" in markdown
    assert "Top card movement reason: Not enough archive history" in markdown
    assert "Recommended next action: Generate one more Thursday archive first" in markdown
    assert pd.read_csv(paths["csv"]).empty


def test_top_card_movement_reason_uses_comparison_csv_when_available(tmp_path) -> None:
    _write_archive(
        tmp_path,
        "2026-07-08T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -120, 0.03, 0.1)],
    )
    _write_archive(
        tmp_path,
        "2026-07-09T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "BETTABLE", "B", 65.0, -110, 0.05, 0.25)],
    )
    comparison = pd.DataFrame([
        {"movement_category": "Odds moved against us", "action_needed": "Review price", "importance_score": 90},
        {"movement_category": "Odds moved in our favor", "action_needed": "Recheck odds", "importance_score": 70},
        {"movement_category": "Edge improved", "action_needed": "Candidate upgrade", "importance_score": 60},
    ])
    comparison.to_csv(tmp_path / "thursday_best_bets_comparison.csv", index=False)

    summary = build_top_card_movement_reason(tmp_path)

    assert summary["top_movement_reason"] == "Mostly odds movement"
    assert "2 of 3" in summary["movement_reason_detail"]


def test_top_card_movement_reason_handles_missing_and_empty_states(tmp_path) -> None:
    missing = build_top_card_movement_reason(tmp_path)
    assert missing["top_movement_reason"] == "Not enough archive history"

    _write_archive(
        tmp_path,
        "2026-07-08T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -120, 0.03, 0.1)],
    )
    _write_archive(
        tmp_path,
        "2026-07-09T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -120, 0.03, 0.1)],
    )

    no_report = build_top_card_movement_reason(tmp_path)
    assert no_report["top_movement_reason"] == "No comparison report yet"

    empty = build_top_card_movement_reason(tmp_path, pd.DataFrame(columns=["movement_category", "action_needed"]))
    assert empty["top_movement_reason"] == "No meaningful movement"

    missing_columns = build_top_card_movement_reason(tmp_path, pd.DataFrame([{"movement_category": "Edge improved"}]))
    assert missing_columns["top_movement_reason"] == "Possible missing odds/data issue"
    assert "action_needed" in missing_columns["movement_reason_detail"]


def test_recommended_next_action_handles_missing_history_and_comparison(tmp_path) -> None:
    no_archives = build_recommended_next_action(tmp_path)
    assert no_archives["recommended_next_action"].startswith("Generate a Thursday archive first")

    _write_archive(
        tmp_path,
        "2026-07-08T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -120, 0.03, 0.1)],
    )
    one_archive = build_recommended_next_action(tmp_path)
    assert one_archive["recommended_next_action"].startswith("Generate one more Thursday archive first")

    _write_archive(
        tmp_path,
        "2026-07-09T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -120, 0.03, 0.1)],
    )
    no_comparison = build_recommended_next_action(tmp_path)
    assert no_comparison["recommended_next_action"].startswith("Generate comparison first")


def test_recommended_next_action_prioritizes_data_removals_prices_and_upgrades(tmp_path) -> None:
    _write_archive(
        tmp_path,
        "2026-07-08T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -120, 0.03, 0.1)],
    )
    _write_archive(
        tmp_path,
        "2026-07-09T12:00:00",
        [_row("Arsenal", "Coventry", "1x2", "home", "LEAN", "C", 52.0, -120, 0.03, 0.1)],
    )

    malformed = build_recommended_next_action(tmp_path, pd.DataFrame([{"movement_category": "Edge improved"}]))
    assert malformed["recommended_next_action"].startswith("Check data/odds first")

    remove = build_recommended_next_action(
        tmp_path,
        pd.DataFrame([{
            "movement_category": "Became PASS/Avoid",
            "action_needed": "Likely remove from card",
            "importance_score": 95,
        }]),
    )
    assert remove["recommended_next_action"].startswith("Review removals first")

    price = build_recommended_next_action(
        tmp_path,
        pd.DataFrame([{
            "movement_category": "Odds moved against us",
            "action_needed": "Review price",
            "importance_score": 80,
        }]),
    )
    assert price["recommended_next_action"].startswith("Review prices first")

    upgrade = build_recommended_next_action(
        tmp_path,
        pd.DataFrame([{
            "movement_category": "Tier upgraded",
            "action_needed": "Candidate upgrade",
            "importance_score": 75,
        }]),
    )
    assert upgrade["recommended_next_action"].startswith("Review candidate upgrades")

    quiet = build_recommended_next_action(
        tmp_path,
        pd.DataFrame(columns=["movement_category", "action_needed", "importance_score"]),
    )
    assert quiet["recommended_next_action"].startswith("No urgent action")
