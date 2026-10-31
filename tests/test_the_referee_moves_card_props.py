"""The appointed referee moves the card props.

Held out on 2025/26-2026/27 (450 matches, walk-forward from 2019/20), each
match's bookings forecast from both teams' card rates improved once multiplied
by the referee's own record against expectation, shrunk toward 1 with 20
matches' worth of league-average evidence: Poisson log likelihood -2.1100 ->
-2.1038, over 3.5 log loss 0.6886 -> 0.6850, over 4.5 0.6641 -> 0.6557. The
spread at K=20 runs from about 0.97 to 1.17.

Football-Data carries the referee of every played match; the Premier League's
own match centre feed (footballapi.pulselive.com, keyless) names the
appointment once it is announced, usually early in match week. No appointment
means no adjustment, never a guessed one.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from epl_betting_lab.data import referee_appointments as appointments
from epl_betting_lab.models.player_props import PlayerPropsModel
from epl_betting_lab.models.referee import (
    REFEREE_SHRINKAGE,
    referee_factors,
    referee_key,
)

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _matches() -> pd.DataFrame:
    teams = ["Arsenal", "Chelsea", "Everton", "Fulham"]
    rows = []
    for i in range(400):
        home, away = teams[i % 4], teams[(i + 1 + i // 4) % 4]
        if home == away:
            away = teams[(i + 2) % 4]
        referee = ["M Oliver", "J Brooks", "A Rookie"][0 if i % 2 else (1 if i < 380 else 2)]
        strict = referee == "J Brooks"
        rows.append({
            "date": pd.Timestamp("2024-08-01") + pd.Timedelta(days=i),
            "home_team": home, "away_team": away, "Referee": referee,
            "HY": 3 if strict else 2, "AY": 3 if strict else 2, "HR": 0, "AR": 0,
        })
    return pd.DataFrame(rows)


def test_a_name_written_two_ways_is_one_referee() -> None:
    assert referee_key("S Attwell") == referee_key("Stuart Attwell") == "s attwell"
    assert referee_key("Michael  Oliver") == referee_key("M Oliver")
    assert referee_key("") == ""


def test_a_strict_referee_reads_above_one_and_is_shrunk() -> None:
    factors = referee_factors(_matches())
    assert REFEREE_SHRINKAGE == 20
    brooks, oliver = factors[referee_key("J Brooks")], factors[referee_key("M Oliver")]
    # 6 cards a match against a league mean of 5: raw 1.2, shrunk a little.
    assert 1.1 < brooks < 1.2
    assert 0.8 < oliver < 1.0


def test_a_referee_with_little_history_stays_near_one() -> None:
    factors = referee_factors(_matches())
    rookie, oliver = factors[referee_key("A Rookie")], factors[referee_key("M Oliver")]
    assert abs(rookie - 1.0) < abs(oliver - 1.0)


def test_the_results_keep_the_referee(tmp_path: Path) -> None:
    from epl_betting_lab.data.fetch_football_data import load_season

    raw = tmp_path / "season.csv"
    pd.DataFrame({
        "Div": ["E0"], "Date": ["16/08/2025"], "HomeTeam": ["Arsenal"], "AwayTeam": ["Chelsea"],
        "FTHG": [1], "FTAG": [0], "FTR": ["H"], "Referee": ["M Oliver"],
    }).to_csv(raw, index=False)
    assert load_season(raw, "2526")["Referee"].tolist() == ["M Oliver"]


LISTING = {"content": [
    {"id": 129006.0, "kickoff": {"millis": 1793449800000},
     "teams": [{"team": {"name": "Chelsea"}}, {"team": {"name": "Manchester United"}}]},
    {"id": 129009.0, "kickoff": {"millis": 1793550600000},
     "teams": [{"team": {"name": "Liverpool"}}, {"team": {"name": "Arsenal"}}]},
]}
DETAIL = {
    129006: {"matchOfficials": [
        {"role": "FOURTH_OFFICIAL", "name": {"display": "Andy Madley"}},
        {"role": "MAIN", "name": {"display": "Jarred Gillett"}},
    ]},
    129009: {"matchOfficials": []},
}


def _fetch(url: str):
    if "/fixtures/" in url:
        return DETAIL[int(url.rsplit("/", 1)[1])]
    if "compseasons" in url:
        return {"content": [{"id": 841.0, "label": "2026/2027"}]}
    return LISTING


def test_the_appointed_referee_is_read_and_an_unannounced_one_is_left_blank() -> None:
    rows = appointments.fetch_appointments(fetch=_fetch)
    by_fixture = {(r["home_team"], r["away_team"]): r["referee"] for r in rows}
    assert by_fixture == {("Chelsea", "Man United"): "Jarred Gillett"}


def test_a_feed_that_cannot_be_read_says_so(tmp_path: Path) -> None:
    def down(url: str):
        raise appointments.AppointmentsError("refused")

    result = appointments.refresh_appointments(
        tmp_path / "appointments.csv", matches=_matches(), fetch=down
    )
    assert "refused" in result and not (tmp_path / "appointments.csv").exists()


def test_the_appointments_file_carries_each_referees_factor(tmp_path: Path) -> None:
    def brooks(url: str):
        if "/fixtures/129006" in url:
            return {"matchOfficials": [{"role": "MAIN", "name": {"display": "John Brooks"}}]}
        return _fetch(url)

    path = tmp_path / "appointments.csv"
    appointments.refresh_appointments(path, matches=_matches(), fetch=brooks)
    (row,) = pd.read_csv(path).to_dict("records")
    assert row["referee"] == "John Brooks" and 1.1 < row["card_factor"] < 1.2


def test_the_factor_scales_only_the_rate_it_is_given() -> None:
    card_props = _load("card_props", ROOT / "tests" / "test_player_card_props.py")
    model = PlayerPropsModel().fit(card_props._league())
    plain = model.over_probability("Hothead", "booked", 0.5, opponent="Everton", venue="home")
    strict = model.over_probability(
        "Hothead", "booked", 0.5, opponent="Everton", venue="home", multiplier=1.17
    )
    assert strict > plain


def test_the_props_card_prices_bookings_with_the_appointed_referee(tmp_path: Path) -> None:
    from epl_betting_lab.reports.player_props_card import build_player_props_card

    card_props = _load("card_props_card", ROOT / "tests" / "test_player_card_props.py")
    staged = [
        card_props._staging_row(market="player_to_receive_card", selection="Yes", american_odds=250),
        card_props._staging_row(),
    ]

    # One market per build: the card keeps one prop per player per match
    # (`_one_stake_per_player`), and this test is about pricing, not that.
    def build(referees: Path | None, rows: list) -> dict:
        return build_player_props_card(
            props_staging_path=card_props._write_csv(
                tmp_path / "props.csv", card_props.STAGING_FIELDS, rows),
            logs_path=card_props._booking_logs(tmp_path),
            policy_path=card_props._policy(
                tmp_path / "policy.json", ["player_to_receive_card", "player_shots_on_target"]),
            referees_path=referees,
            run_at=card_props.RUN_AT,
        )

    def picks(referees: Path | None) -> dict:
        found = {}
        for row in staged:
            found.update({p["market"]: p for p in build(referees, [row])["picks"]})
        return found

    lenient = tmp_path / "referees.csv"
    pd.DataFrame([{"home_team": "Newcastle", "away_team": "Liverpool",
                   "referee": "Michael Oliver", "card_factor": 0.8}]).to_csv(lenient, index=False)
    without = picks(tmp_path / "absent.csv")
    with_ref = picks(lenient)
    booked, shots = "player_to_receive_card", "player_shots_on_target"
    assert with_ref[booked]["model_probability"] < without[booked]["model_probability"]
    assert with_ref[booked]["referee"] == "Michael Oliver"
    assert with_ref[shots]["model_probability"] == without[shots]["model_probability"]
    assert without[booked]["referee"] == ""


def test_the_card_names_the_referee_it_priced_with() -> None:
    from epl_betting_lab.reports.player_props_card import render_player_props_markdown

    pick = {"home_team": "Newcastle", "away_team": "Liverpool", "market": "player_to_receive_card",
            "player": "Bruno Guimaraes", "selection": "Yes", "model_probability": 0.3, "edge": 0.1,
            "american_odds": 250.0, "book": "Bovada", "units": 0.1,
            "referee": "Michael Oliver", "referee_factor": 0.97}
    text = render_player_props_markdown({"status": "Props card ready", "picks": [pick]})
    assert "Michael Oliver, x0.97" in text
