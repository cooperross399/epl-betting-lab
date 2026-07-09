from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.thursday_decision_queue import (
    build_thursday_decision_queue,
    render_thursday_decision_queue,
    save_thursday_decision_queue,
)


def _comparison_rows() -> list[dict[str, object]]:
    return [
        {
            "action_needed": "Watch only",
            "action_reason": "The play slipped but is not a full remove yet.",
            "movement_category": "Fell to LEAN",
            "importance_score": 95.0,
            "home_team": "Chelsea",
            "away_team": "Fulham",
            "market": "1x2",
            "selection": "home",
            "previous_status": "BETTABLE",
            "latest_status": "LEAN",
            "previous_confidence_tier": "B",
            "latest_confidence_tier": "C",
            "previous_american_odds": -125,
            "latest_american_odds": -130,
            "calibrated_edge_change": -0.02,
            "suggested_units_change": -0.15,
        },
        {
            "action_needed": "Candidate upgrade",
            "action_reason": "Edge improved and the play is now stronger.",
            "movement_category": "Tier upgraded",
            "importance_score": 70.0,
            "home_team": "Arsenal",
            "away_team": "Coventry",
            "market": "1x2",
            "selection": "home",
            "previous_status": "LEAN",
            "latest_status": "BETTABLE",
            "previous_confidence_tier": "C",
            "latest_confidence_tier": "B",
            "previous_american_odds": -120,
            "latest_american_odds": -110,
            "calibrated_edge_change": 0.03,
            "suggested_units_change": 0.15,
        },
        {
            "action_needed": "Review price",
            "action_reason": "Odds moved against us, so confirm the current number.",
            "movement_category": "Odds moved against us",
            "importance_score": 90.0,
            "home_team": "Liverpool",
            "away_team": "Leeds",
            "market": "total_2_5",
            "selection": "over",
            "previous_status": "BETTABLE",
            "latest_status": "BETTABLE",
            "previous_confidence_tier": "A",
            "latest_confidence_tier": "A",
            "previous_american_odds": 105,
            "latest_american_odds": -115,
            "calibrated_edge_change": -0.01,
            "suggested_units_change": 0.0,
        },
        {
            "action_needed": "Candidate upgrade",
            "action_reason": "The play became BETTABLE.",
            "movement_category": "Became BETTABLE",
            "importance_score": 100.0,
            "home_team": "Spurs",
            "away_team": "Wolves",
            "market": "1x2",
            "selection": "home",
            "previous_status": "LEAN",
            "latest_status": "BETTABLE",
            "previous_confidence_tier": "C",
            "latest_confidence_tier": "A",
            "previous_american_odds": -135,
            "latest_american_odds": -120,
            "calibrated_edge_change": 0.06,
            "suggested_units_change": 0.4,
        },
    ]


def test_decision_queue_groups_by_action_then_importance(tmp_path) -> None:
    pd.DataFrame(_comparison_rows()).to_csv(tmp_path / "thursday_best_bets_comparison.csv", index=False)

    queue, summary = build_thursday_decision_queue(tmp_path)

    assert summary["available"] is True
    assert list(queue["action_needed"]) == ["Candidate upgrade", "Candidate upgrade", "Review price", "Watch only"]
    assert list(queue["home_team"].head(2)) == ["Spurs", "Arsenal"]
    assert queue.iloc[0]["importance_score"] == 100.0


def test_decision_queue_markdown_shows_grouped_review_fields(tmp_path) -> None:
    pd.DataFrame(_comparison_rows()).to_csv(tmp_path / "thursday_best_bets_comparison.csv", index=False)
    queue, summary = build_thursday_decision_queue(tmp_path)

    markdown = render_thursday_decision_queue(queue, summary)

    assert "Thursday Decision Queue" in markdown
    assert "## Candidate upgrade" in markdown
    assert "Review order" in markdown
    assert "Status: LEAN -> BETTABLE" in markdown
    assert "Edge change: +0.060" in markdown
    assert "Unit change: +0.400" in markdown


def test_save_decision_queue_handles_missing_comparison(tmp_path) -> None:
    paths = save_thursday_decision_queue(tmp_path)

    assert paths["csv"].name == "thursday_decision_queue.csv"
    assert paths["markdown"].name == "thursday_decision_queue.md"
    assert paths["csv"].exists()
    assert paths["markdown"].exists()
    assert pd.read_csv(paths["csv"]).empty
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "comparison report is missing" in markdown
    assert "python scripts/compare_thursday_best_bets.py" in markdown
