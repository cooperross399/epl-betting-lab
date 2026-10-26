"""A league feed that times out must not silently cost the European sections.

On 2026-10-19 Football-Data timed out on Serie A, Ligue 1, the Greek and the
Scottish leagues. The European pool needs every domestic league, so the
Champions League, Europa League and Conference League sections could not be
built, and the card dropped all three without a word: the reason was printed
only in the run log. Two fixes. The leagues' datasets travel in the run's
saved state, so a feed that fails falls back to the previous run's file; and a
competition that still cannot be built is named on the card with the reason.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.extra_competitions_card import ExtraCard, render_extra_card

ROOT = Path(__file__).resolve().parents[1]


def test_a_competition_that_could_not_be_built_is_named_with_the_reason() -> None:
    card = ExtraCard(pd.DataFrame(), notes=["No selection cleared the rules."], priced=5)
    report = "\n".join(render_extra_card(
        {"EFLC": card}, unbuilt={"UCL": "No dataset for F1", "UEL": "No dataset for F1"},
    ))
    assert "Could not be built this run" in report
    assert "UEFA Champions League" in report and "UEFA Europa League" in report
    assert "No dataset for F1" in report


def test_nothing_is_said_when_everything_built() -> None:
    card = ExtraCard(pd.DataFrame(), notes=[], priced=5)
    assert "Could not be built" not in "\n".join(render_extra_card({"EFLC": card}))


def test_the_script_writes_the_section_even_when_every_competition_failed(tmp_path, monkeypatch) -> None:
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("build_extra_card", ROOT / "scripts" / "build_extra_card.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    def broken(*args, **kwargs):
        raise FileNotFoundError("No dataset for F1")

    monkeypatch.setattr(script, "build_extra_card", broken)
    feed = tmp_path / "feed.csv"
    pd.DataFrame({"competition": ["UCL"], "home_team": ["A"], "away_team": ["B"]}).to_csv(feed, index=False)
    out = tmp_path / "extra.md"
    monkeypatch.setattr(sys, "argv", ["build_extra_card.py", "--feed", str(feed), "--out", str(out)])
    assert script.main() == 0
    text = out.read_text()
    assert "Could not be built this run" in text and "No dataset for F1" in text


def test_the_league_datasets_travel_in_the_saved_state() -> None:
    text = (ROOT / ".github" / "workflows" / "matchday-refresh.yml").read_text(encoding="utf-8")
    block = text.split("name: matchday-state", 1)[1].split("retention-days", 1)[0]
    assert "data/processed/football_data_*_matches.csv" in block
