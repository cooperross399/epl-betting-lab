"""This season's European results reach the European ratings.

The European pool rates the cup and European picks, and the only bridge
between its eleven countries is the European ties themselves. Until
2026-10-26 those came from openfootball alone, over a season list that was
typed in and stopped at 2025-26. openfootball has not published the 2025-26
Europa League or Conference League, nor anything of 2026-27. So the ratings
behind the Champions League picks had learnt nothing from the 144 European
matches played this season, or from about 360 Europa and Conference League
matches the season before.

ESPN's keyless scoreboard carries every one of them. It fills a
(season, competition) that openfootball does not publish, and only those, so
no tie is counted twice.
"""

from __future__ import annotations

import pandas as pd
import pytest

from epl_betting_lab.config import CURRENT_SEASON
from epl_betting_lab.data import european_results
from epl_betting_lab.data.european_clubs import espn_name
from epl_betting_lab.data.european_results import (
    EuropeanResultsUnavailable,
    espn_season_ties,
    load_european_ties,
)
from epl_betting_lab.models import european_ratings
from epl_betting_lab.models.european_ratings import build_european_pool


def _event(home: str, away: str, score: tuple[int, int], *, when: str = "2026-10-21T19:00Z",
           season: int = 2026, completed: bool = True) -> dict:
    return {
        "date": when,
        "season": {"year": season},
        "status": {"type": {"completed": completed}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": str(score[0]), "team": {"displayName": home}},
            {"homeAway": "away", "score": str(score[1]), "team": {"displayName": away}},
        ]}],
    }


SCOREBOARD = {"events": [
    _event("Paris Saint-Germain", "Internazionale", (2, 1)),
    _event("Nottingham Forest", "Real Betis", (1, 1), when="2026-10-22T19:00Z"),
    _event("Arsenal", "Bayern Munich", (3, 0), completed=False),
    _event("Liverpool", "Napoli", (2, 0), season=2025, when="2026-02-18T20:00Z"),
]}


def test_the_season_list_reaches_the_season_being_played() -> None:
    """Typed in, it stopped at 2025-26 and nothing said so."""
    current = f"20{CURRENT_SEASON[:2]}-{CURRENT_SEASON[2:]}"
    assert european_results.SEASONS[-1] == current
    assert european_results.SEASONS[0] == "2019-20"


def test_espn_names_go_to_football_data_names() -> None:
    assert espn_name("Paris Saint-Germain") == "Paris SG"
    assert espn_name("Internazionale") == "Inter"
    assert espn_name("Nottingham Forest") == "Nott'm Forest"
    assert espn_name("Real Betis") == "Betis"
    # A name that already agrees passes through, as the provider map does.
    assert espn_name("Arsenal") == "Arsenal"


def test_only_completed_ties_of_that_season_become_rows() -> None:
    ties = espn_season_ties([SCOREBOARD], "2026-27", "UEL")
    assert sorted(zip(ties["home_team"], ties["away_team"])) == [
        ("Nott'm Forest", "Betis"), ("Paris SG", "Inter"),
    ]
    psg = ties[ties["home_team"] == "Paris SG"].iloc[0]
    assert (psg["home_goals"], psg["away_goals"]) == (2, 1)
    assert psg["competition"] == "UEL" and psg["season"] == "2026-27"
    assert psg["date"] == pd.Timestamp("2026-10-21")


def test_espn_fills_only_what_openfootball_does_not_publish() -> None:
    asked: list[tuple[str, str]] = []

    def openfootball(season: str, competition: str = "UCL") -> str:
        if season == "2026-27":
            raise EuropeanResultsUnavailable("404")
        return "  Tue Sep 19 2023\n    18:45  AC Milan (ITA) v Newcastle United FC (ENG)  0-0\n"

    def espn(season: str, competition: str) -> list[dict]:
        asked.append((season, competition))
        return [SCOREBOARD]

    parsed = load_european_ties(
        ("2023-24", "2026-27"), ("UCL",), fetcher=openfootball, espn_fetcher=espn
    )
    assert asked == [("2026-27", "UCL")]
    assert set(parsed.matches["season"]) == {"2023-24", "2026-27"}
    assert len(parsed.matches[parsed.matches["season"] == "2026-27"]) == 2


def test_both_sources_failing_costs_only_that_competition() -> None:
    def gone(season: str, competition: str = "UCL") -> str:
        raise EuropeanResultsUnavailable("404")

    def espn(season: str, competition: str) -> list[dict]:
        if competition == "UECL":
            raise EuropeanResultsUnavailable("ESPN down")
        return [SCOREBOARD]

    parsed = load_european_ties(("2026-27",), ("UEL", "UECL"), fetcher=gone, espn_fetcher=espn)
    assert set(parsed.matches["competition"]) == {"UEL"}


def test_the_pool_names_the_clubs_whose_ties_it_could_not_rate(monkeypatch, tmp_path) -> None:
    """A club the pool does not hold costs its ties. Which clubs did is said,
    so a name written down wrong shows up instead of quietly losing a bridge."""
    domestic = pd.DataFrame({
        "date": ["2026-09-01", "2026-09-02"],
        "home_team": ["Paris SG", "Inter"],
        "away_team": ["Lyon", "Milan"],
        "home_goals": [1, 2], "away_goals": [0, 2],
    })
    for code in ("F1", "I1"):
        domestic.to_csv(tmp_path / f"{code}.csv", index=False)
    monkeypatch.setattr(european_ratings, "processed_path_for", lambda code: tmp_path / f"{code}.csv")
    ties = espn_season_ties([SCOREBOARD], "2026-27", "UEL")

    pool = build_european_pool({"FRA": "F1", "ITA": "I1"}, ties=ties)
    assert pool.ties == 1
    assert pool.unrated_clubs == ["Betis", "Nott'm Forest"]
