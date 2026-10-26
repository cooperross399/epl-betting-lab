"""A player FPL lists as injured, suspended or unlikely to play is not priced.

The props model rates a player on his last six appearances' minutes and knows
nothing about his fitness. Fantasy Premier League's bootstrap, which the props
refresh already downloads for tackles and saves, carries each player's status
and a percentage chance of playing the next round, with the news line behind
it. Until 2026-10-26 none of it was read. So the card could price an over on a
striker ruled out on Friday, at a stake that the book either voids or, on an
under, settles against a player who never came on.

`chance_of_playing_next_round` of 50 or less (or a status of injured,
suspended or unavailable) withholds the player's props. The card names who
and why. No player is priced up or down for a knock: a 75% player keeps his
normal rate.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from epl_betting_lab.providers.fpl_players import (
    FPL_AVAILABILITY_FILENAME,
    build_fpl_availability,
    write_fpl_data,
    FplFetchResult,
)
from epl_betting_lab.reports.player_props_card import (
    build_player_props_card,
    render_player_props_markdown,
)

RUN_AT = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)

BOOTSTRAP = {
    "teams": [{"id": 1, "name": "Newcastle"}, {"id": 2, "name": "Liverpool"}],
    "element_types": [{"id": 4, "singular_name_short": "FWD"}],
    "elements": [
        {"id": 10, "first_name": "Alexander", "second_name": "Isak", "team": 1,
         "status": "i", "chance_of_playing_next_round": 0,
         "news": "Groin injury - Expected back 01 Nov", "minutes": 900},
        {"id": 11, "first_name": "Anthony", "second_name": "Gordon", "team": 1,
         "status": "d", "chance_of_playing_next_round": 75,
         "news": "Knock - 75% chance of playing", "minutes": 900},
        {"id": 12, "first_name": "Harvey", "second_name": "Barnes", "team": 1,
         "status": "a", "chance_of_playing_next_round": None, "news": "", "minutes": 900},
    ],
}


def test_the_bootstrap_becomes_an_availability_table() -> None:
    table = build_fpl_availability(BOOTSTRAP)
    isak = table[table["player"] == "Alexander Isak"].iloc[0]
    assert isak["team"] == "Newcastle"
    assert isak["status"] == "i" and int(isak["chance_next_round"]) == 0
    assert "Groin" in isak["news"]
    barnes = table[table["player"] == "Harvey Barnes"].iloc[0]
    assert pd.isna(barnes["chance_next_round"])


def test_the_refresh_writes_it_beside_the_logs(tmp_path: Path) -> None:
    result = FplFetchResult()
    result.availability = build_fpl_availability(BOOTSTRAP)
    write_fpl_data(result, tmp_path)
    written = pd.read_csv(tmp_path / FPL_AVAILABILITY_FILENAME)
    assert len(written) == 3


LOG_FIELDS = ["season", "date", "match_id", "team", "opponent", "venue", "player", "player_id",
              "position", "minutes", "goals", "assists", "shots", "shots_on_target",
              "yellow_cards", "red_cards", "first_goal_minute"]
STAGING_FIELDS = ["date", "commence_time", "home_team", "away_team", "market", "player",
                  "selection", "american_odds", "book", "notes"]


def _csv(path: Path, fields: list[str], rows: list[dict]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({f: row.get(f, "") for f in fields})
    return path


def _card(tmp_path: Path, availability: Path | None):
    rows = []
    for m in range(12):
        for name in ("Alexander Isak", "Anthony Gordon", "Harvey Barnes"):
            rows.append({"season": "2026", "date": f"2026-08-{m + 1:02d}", "match_id": f"m{m}",
                         "team": "Newcastle", "opponent": "Everton", "venue": "home",
                         "player": name, "player_id": name, "position": "FW", "minutes": 90,
                         "goals": 1, "assists": 0, "shots": 4, "shots_on_target": 3,
                         "yellow_cards": 0, "red_cards": 0})
        for p in range(6):
            rows.append({"season": "2026", "date": f"2026-08-{m + 1:02d}", "match_id": f"m{m}",
                         "team": "Everton", "opponent": "Newcastle", "venue": "away",
                         "player": f"Squad {p}", "player_id": f"sq{p}", "position": "MC",
                         "minutes": 90, "shots": 1, "shots_on_target": 1})
    staging = [
        {"date": "2026-08-23", "commence_time": "2026-08-23T15:00:00Z", "home_team": "Newcastle",
         "away_team": "Liverpool", "market": "player_shots_on_target", "player": name,
         "selection": "Over@0.5", "american_odds": 150, "book": "FanDuel"}
        for name in ("Alexander Isak", "Anthony Gordon", "Harvey Barnes")
    ]
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"provider_allowlist_entries": {"the_odds_api": {
        "allowlist_status": "allowed", "reviewer_name": "cooperross399",
        "evidence_receipt_id": "odds_api-20260821T114655-0400-20ffa5677988",
        "required_markets": ["player_shots_on_target"]}}}))
    return build_player_props_card(
        props_staging_path=_csv(tmp_path / "props.csv", STAGING_FIELDS, staging),
        logs_path=_csv(tmp_path / "logs.csv", LOG_FIELDS, rows),
        policy_path=policy,
        availability_path=availability,
        run_at=RUN_AT,
    )


def _availability(tmp_path: Path) -> Path:
    path = tmp_path / FPL_AVAILABILITY_FILENAME
    build_fpl_availability(BOOTSTRAP).to_csv(path, index=False)
    return path


def test_a_player_ruled_out_is_not_priced(tmp_path: Path) -> None:
    summary = _card(tmp_path, _availability(tmp_path))
    priced = {p["player"] for p in summary["picks"]}
    assert "Alexander Isak" not in priced
    # A 75% knock keeps his normal rate; a fit player is untouched.
    assert {"Anthony Gordon", "Harvey Barnes"} <= priced


def test_the_card_says_who_was_withheld_and_why(tmp_path: Path) -> None:
    summary = _card(tmp_path, _availability(tmp_path))
    (withheld,) = summary["withheld_unavailable"]
    assert withheld["player"] == "Alexander Isak"
    assert "Groin" in withheld["news"]
    assert "Alexander Isak" in render_player_props_markdown(summary)


def test_without_the_table_every_player_is_priced_as_before(tmp_path: Path) -> None:
    summary = _card(tmp_path, tmp_path / "absent.csv")
    assert len(summary["picks"]) == 3
    assert summary["withheld_unavailable"] == []
