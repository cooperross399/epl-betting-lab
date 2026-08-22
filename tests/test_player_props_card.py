"""The props card: held by policy until a review says otherwise."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from epl_betting_lab.reports.player_props_card import (
    HELD_STATUS,
    NO_STAGING_STATUS,
    READY_STATUS,
    build_player_props_card,
    save_player_props_card,
)


RUN_AT = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)

LOG_FIELDS = [
    "season",
    "date",
    "match_id",
    "team",
    "opponent",
    "venue",
    "player",
    "player_id",
    "position",
    "minutes",
    "goals",
    "assists",
    "shots",
    "shots_on_target",
    "yellow_cards",
    "red_cards",
    "first_goal_minute",
]

STAGING_FIELDS = [
    "date",
    "commence_time",
    "home_team",
    "away_team",
    "market",
    "player",
    "selection",
    "american_odds",
    "book",
    "notes",
]


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return path


def _policy(path: Path, markets: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "provider_allowlist_entries": {
                    "the_odds_api": {"required_markets": markets}
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def _logs(tmp_path: Path) -> Path:
    rows = []
    for m in range(12):
        rows.append(
            {
                "season": "2026",
                "date": f"2026-08-{m + 1:02d}",
                "match_id": f"m{m}",
                "team": "Newcastle",
                "opponent": "Everton",
                "venue": "home",
                "player": "Alexander Isak",
                "player_id": "isak",
                "position": "FW",
                "minutes": 90,
                "goals": 1,
                "assists": 0,
                "shots": 4,
                "shots_on_target": 3,
                "yellow_cards": 0,
                "red_cards": 0,
                "first_goal_minute": 30,
            }
        )
        for p in range(6):
            rows.append(
                {
                    "season": "2026",
                    "date": f"2026-08-{m + 1:02d}",
                    "match_id": f"m{m}",
                    "team": "Everton",
                    "opponent": "Newcastle",
                    "venue": "away",
                    "player": f"Squad {p}",
                    "player_id": f"sq{p}",
                    "position": "MC",
                    "minutes": 90,
                    "goals": 0,
                    "assists": 0,
                    "shots": 1,
                    "shots_on_target": 1,
                    "yellow_cards": 0,
                    "red_cards": 0,
                    "first_goal_minute": "",
                }
            )
    return _write_csv(tmp_path / "logs.csv", LOG_FIELDS, rows)


def _staging_row(**overrides) -> dict:
    row = {
        "date": "2026-08-23",
        "commence_time": "2026-08-23T15:00:00Z",
        "home_team": "Newcastle",
        "away_team": "Liverpool",
        "market": "player_shots_on_target",
        "player": "Alexander Isak",
        "selection": "Over@0.5",
        "american_odds": 150,
        "book": "FanDuel",
        "notes": "",
    }
    row.update(overrides)
    return row


def _build(tmp_path: Path, *, markets: list[str], staging_rows: list[dict]):
    return build_player_props_card(
        props_staging_path=_write_csv(
            tmp_path / "props.csv", STAGING_FIELDS, staging_rows
        ),
        logs_path=_logs(tmp_path),
        policy_path=_policy(tmp_path / "policy.json", markets),
        run_at=RUN_AT,
    )


class TestHeldByPolicy:
    def test_the_shipped_policy_holds_every_prop(self, tmp_path: Path) -> None:
        """Today's real policy approves eight match markets and no props."""
        summary = build_player_props_card(
            props_staging_path=tmp_path / "absent.csv",
            logs_path=tmp_path / "absent_logs.csv",
            run_at=RUN_AT,
        )

        assert summary["status"] == HELD_STATUS
        assert summary["picks"] == []
        assert "no-value" in str(summary["note"]) or "no value" in str(
            summary["note"]
        )

    def test_held_still_reports_which_markets_hold_prices(
        self, tmp_path: Path
    ) -> None:
        """That list is the evidence a future approval binds to."""
        summary = _build(
            tmp_path, markets=["1x2"], staging_rows=[_staging_row()]
        )

        assert summary["status"] == HELD_STATUS
        assert summary["markets_with_staged_prices"] == [
            "player_shots_on_target"
        ]
        assert summary["picks"] == []


class TestApprovedProps:
    def test_an_approved_market_produces_a_corrected_pick(
        self, tmp_path: Path
    ) -> None:
        summary = _build(
            tmp_path,
            markets=["player_shots_on_target"],
            staging_rows=[_staging_row()],
        )

        assert summary["status"] == READY_STATUS
        assert len(summary["picks"]) == 1
        pick = summary["picks"][0]
        assert pick["player"] == "Alexander Isak"
        assert pick["units"] == 0.1
        # Isak's raw SOT expectation is ~3 per match; even corrected, the
        # over-0.5 probability towers over the +150 implied 40%.
        assert pick["model_probability"] > 0.8
        assert pick["edge"] > 0.08

    def test_an_unapproved_market_stays_out_even_with_prices(
        self, tmp_path: Path
    ) -> None:
        rows = [
            _staging_row(),
            _staging_row(
                market="player_goal_scorer_anytime", selection="Yes"
            ),
        ]
        summary = _build(
            tmp_path, markets=["player_shots_on_target"], staging_rows=rows
        )

        assert {p["market"] for p in summary["picks"]} == {
            "player_shots_on_target"
        }

    def test_the_best_book_wins(self, tmp_path: Path) -> None:
        rows = [
            _staging_row(american_odds=140, book="FanDuel"),
            _staging_row(american_odds=165, book="DraftKings"),
        ]
        summary = _build(
            tmp_path, markets=["player_shots_on_target"], staging_rows=rows
        )

        assert len(summary["picks"]) == 1
        assert summary["picks"][0]["book"] == "DraftKings"
        assert summary["picks"][0]["american_odds"] == 165

    def test_a_player_the_logs_know_elsewhere_is_skipped(
        self, tmp_path: Path
    ) -> None:
        """A transfer the data has not caught up with gets no opinion, not a
        wrong one."""
        rows = [
            _staging_row(
                home_team="Fulham", away_team="Chelsea"
            )
        ]
        summary = _build(
            tmp_path, markets=["player_shots_on_target"], staging_rows=rows
        )

        assert summary["picks"] == []

    def test_a_past_fixture_is_never_priced(self, tmp_path: Path) -> None:
        rows = [_staging_row(date="2026-08-20")]
        summary = _build(
            tmp_path, markets=["player_shots_on_target"], staging_rows=rows
        )

        assert summary["picks"] == []

    def test_approved_without_staging_says_so(self, tmp_path: Path) -> None:
        summary = build_player_props_card(
            props_staging_path=tmp_path / "absent.csv",
            logs_path=_logs(tmp_path),
            policy_path=_policy(
                tmp_path / "policy.json", ["player_shots_on_target"]
            ),
            run_at=RUN_AT,
        )

        assert summary["status"] == NO_STAGING_STATUS
        assert summary["picks"] == []


class TestReports:
    def test_reports_are_written_with_the_standing_caveat(
        self, tmp_path: Path
    ) -> None:
        result = save_player_props_card(
            output_dir=tmp_path / "out",
            props_staging_path=_write_csv(
                tmp_path / "props.csv", STAGING_FIELDS, [_staging_row()]
            ),
            logs_path=_logs(tmp_path),
            policy_path=_policy(
                tmp_path / "policy.json", ["player_shots_on_target"]
            ),
            run_at=RUN_AT,
        )
        markdown = Path(result["markdown"]).read_text(encoding="utf-8")

        assert "no edge" in markdown
        assert "team sheet" in markdown
        assert Path(result["json"]).is_file()


class TestApprovability:
    def test_prop_markets_are_approvable_but_not_approved(self) -> None:
        from epl_betting_lab.providers.player_props_staging import (
            PROP_EVENT_MARKETS,
        )
        from epl_betting_lab.reports.github_approval import APPROVABLE_MARKETS
        from epl_betting_lab.reports.player_props_card import (
            approved_prop_markets,
        )

        for market in PROP_EVENT_MARKETS:
            assert market in APPROVABLE_MARKETS
        # The shipped policy approves none of them.
        assert approved_prop_markets() == []
