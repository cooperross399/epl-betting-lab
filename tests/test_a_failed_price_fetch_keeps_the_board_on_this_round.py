"""A run with no provider prices must not send the public board back to August.

2026-10-10: the odds quota ran out, the provider answered 401, and no staging
file was written. `save_automated_card_input` then died on `staged`, which is
only bound when staging exists, so this run's `automated_card_input.json` was
never written and the card read the copy committed on 2026-08-21 — window
"2026-08-21 through 2026-08-24". The card was archived as the newest one, the
board took its window from it, and epl.maverickhightower.com published the
opening round, every fixture "started", no picks, while the 09:07 card for
the real round sat one directory older in the archive.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timezone
from pathlib import Path

from epl_betting_lab.reports.automated_card_input import save_automated_card_input

BUILDER = Path(__file__).resolve().parents[1] / "web" / "build_board_json.py"


def _builder():
    spec = importlib.util.spec_from_file_location("build_board_json_failed_fetch", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_card_input_with_no_staging_reports_blocked_instead_of_crashing(tmp_path: Path) -> None:
    result = save_automated_card_input(
        staging_odds_path=tmp_path / "missing_odds.csv",
        staging_fixtures_path=tmp_path / "missing_fixtures.csv",
        output_dir=tmp_path / "outputs",
        card_input_path=tmp_path / "staging" / "card_input.csv",
        policy_path=tmp_path / "no_policy.json",
        mapping_verified=False,
        validation_passed=False,
        freshness_passed=False,
        now=datetime(2026, 10, 10, 10, 45, tzinfo=timezone.utc),
    )
    summary = result["summary"]
    assert summary["status"] == "Blocked"
    assert summary["blockers"]
    # Written this run, so nothing downstream reads a stale committed copy.
    written = json.loads((tmp_path / "outputs" / "automated_card_input.json").read_text())
    assert written["generated_at"].startswith("2026-10-10")
    assert "2026-08-21" not in written["window_label"]


def _archive(lab: Path, stamp: str, card: dict) -> None:
    day, time = stamp.split("/")
    path = lab / "data" / "outputs" / "archive" / "automated_cards" / day / time / "automated_card.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card), encoding="utf-8")


GOOD = {"card_generated": True, "window_label": "2026-10-10 through 2026-10-12",
        "best_bets": [{"home_team": "Arsenal", "away_team": "Everton", "market": "btts",
                       "selection": "yes", "american_odds": "-110", "calibrated_edge": "0.05"}]}
FAILED = {"card_generated": False, "window_label": "2026-08-21 through 2026-08-24",
          "root_blocker": "Provider-derived card input missing: `automated_card_current_odds.csv`."}


def test_the_board_reads_the_newest_card_that_generated_for_a_live_round(tmp_path: Path) -> None:
    _archive(tmp_path, "2026-10-10/090700", GOOD)
    _archive(tmp_path, "2026-10-10/104530", FAILED)
    card, source = _builder().read_card(tmp_path, today=date(2026, 10, 10))
    assert card["window_label"] == GOOD["window_label"], source
    assert source.endswith("2026-10-10/090700/automated_card.json")


def test_a_generated_card_for_a_round_already_over_is_not_preferred(tmp_path: Path) -> None:
    _archive(tmp_path, "2026-10-03/090700", {**GOOD, "window_label": "2026-10-03 through 2026-10-05"})
    _archive(tmp_path, "2026-10-10/104530", FAILED)
    card, _ = _builder().read_card(tmp_path, today=date(2026, 10, 10))
    assert card["card_generated"] is False


def test_a_card_that_did_not_generate_does_not_choose_the_window() -> None:
    builder = _builder()
    assert builder.card_window(FAILED) is None
    assert builder.card_window(GOOD) == (date(2026, 10, 10), date(2026, 10, 12))
