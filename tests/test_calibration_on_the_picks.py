"""Calibration is read on the picks, and the card trusts the model only as far
as the picks earned (the CBB lab's winner's-curse finding and trust table)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from epl_betting_lab.reports.selection_calibration import (
    MIN_PICKS_FOR_TRUST,
    load_trust_weights,
    measure,
    trust_weight,
    cell,
)
from epl_betting_lab.reports.thursday_best_bets import LEAN_TIER, build_thursday_best_bets


def _population(seed: int = 3, n: int = 4000) -> pd.DataFrame:
    """Calibrated overall, overconfident where the model disagrees most."""
    rng = np.random.default_rng(seed)
    truth = rng.uniform(0.35, 0.65, n)
    noise = rng.normal(0, 0.06, n)
    model = np.clip(truth + noise, 0.05, 0.95)
    won = rng.uniform(size=n) < truth
    implied = truth + 0.02  # the price knows the truth, plus a margin
    american = np.where(implied >= 0.5, -100 * implied / (1 - implied), 100 * (1 - implied) / implied)
    frame = pd.DataFrame(
        {"market": "draw_no_bet", "calibrated_model_prob": model, "won": won,
         "push": False, "american_odds": american}
    )
    frame["edge"] = model - implied
    return frame


def test_the_whole_population_looks_calibrated_and_the_picks_do_not():
    scored = _population()
    picked = scored[scored["edge"] > 0.05]
    result = measure(scored, picked, source="synthetic")["draw_no_bet"]
    assert abs(result["all"]["gap_points"]) < 2.0
    assert result["picked"]["gap_points"] > 4.0
    assert 0 <= result["trust_weight"] < 0.5


def test_too_few_picks_set_no_weight():
    picked = _population().head(MIN_PICKS_FOR_TRUST - 1)
    assert trust_weight(cell(picked)) is None


def test_a_missing_file_moves_nothing(tmp_path: Path):
    assert load_trust_weights(tmp_path / "absent.json") == {}


def _bet(market, edge, home="Newcastle", away="Everton"):
    return {
        "home_team": home, "away_team": away, "market": market, "selection": "home",
        "status": "BETTABLE", "american_odds": -130, "raw_model_prob": 0.6,
        "calibrated_model_prob": 0.6, "model_prob": 0.6, "raw_edge": edge,
        "calibrated_edge": edge, "edge": edge, "fair_american": -150, "book": "FanDuel",
    }


def _weights(tmp_path: Path, weights: dict[str, float]) -> Path:
    path = tmp_path / "selection_calibration.json"
    path.write_text(json.dumps({"markets": {m: {"trust_weight": w} for m, w in weights.items()}}))
    return path


def test_the_card_pulls_a_pick_toward_the_price_by_its_weight(tmp_path: Path):
    path = _weights(tmp_path, {"draw_no_bet": 0.5})
    candidates = pd.DataFrame([
        _bet("draw_no_bet", 0.06),
        _bet("double_chance", 0.06, home="Chelsea", away="Fulham"),
    ])
    report = build_thursday_best_bets(candidates, trust_weights_path=path)
    dnb = report[report["market"] == "draw_no_bet"].iloc[0]
    # 0.5 x 6% = 3% is under the 3.5% bar: shown, unstaked, with the reason.
    assert dnb["section"] == "Leans"
    assert dnb["confidence_tier"] == LEAN_TIER
    assert dnb["suggested_units"] == 0
    assert "trust" in dnb["qualifies_reason"]
    # A market with no weight is untouched.
    dc = report[report["market"] == "double_chance"].iloc[0]
    assert dc["section"] == "Best bets"


def test_a_pick_that_still_clears_the_bar_keeps_its_stake(tmp_path: Path):
    path = _weights(tmp_path, {"draw_no_bet": 0.8})
    report = build_thursday_best_bets(pd.DataFrame([_bet("draw_no_bet", 0.06)]), trust_weights_path=path)
    assert report.iloc[0]["section"] == "Best bets"
    assert report.iloc[0]["suggested_units"] == 0.1


def _matchday() -> str:
    return (Path(__file__).resolve().parents[1] / ".github/workflows/matchday-refresh.yml").read_text()


def test_the_refresh_measures_the_picks_before_the_card_is_built():
    text = _matchday()
    measure_at = text.index("- name: Measure calibration on the picks")
    assert measure_at < text.index("- name: Rebuild every report")
    block = text[measure_at:].split("\n      - name:", 1)[0]
    assert "continue-on-error: true" in block
    assert "FEED_BRANCH=odds-history" in block
    assert "scripts/run_selection_calibration.py" in block


def test_the_weights_travel_to_the_next_run_and_the_report_is_uploaded():
    text = _matchday()
    state = text.split("name: matchday-state", 1)[1].split("retention-days", 1)[0]
    reports = text.split("name: matchday-reports", 1)[1].split("retention-days", 1)[0]
    assert "data/outputs/selection_calibration.json" in state
    assert "data/outputs/selection_calibration.md" in reports


def test_the_runner_writes_nothing_without_bought_prices(tmp_path: Path):
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        [sys.executable, str(root / "scripts/run_selection_calibration.py"),
         "--odds", str(tmp_path / "absent.csv"), "--json", str(tmp_path / "w.json"),
         "--markdown", str(tmp_path / "w.md")],
        capture_output=True, text=True, env={"PYTHONPATH": str(root / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert out.returncode == 0, out.stderr
    assert not (tmp_path / "w.json").exists()
    assert "no bought prices" in out.stdout
