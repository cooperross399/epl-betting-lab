"""Props is the third section the card publishes and no audit could see it.

Two halves of the same hole:

  * `player_props_staging` writes `commence_time` — the provider's exact
    kick-off — into every row, and `build_player_props_card` never read it.
    The only staleness filter was the date-string compare
    `frame["date"] >= today`, under which a fixture that kicked off at 12:30
    is still offered by the 15:00 run, because "2026-10-03" >= "2026-10-03".
  * `audit_card_freshness` opened `automated_card.json` and
    `extra_competitions_card.json` and not the props card, so its verdict —
    published to the card-feed branch as the run's freshness answer — read
    `faults: 0, clean: true` about a population props was never in.

That is the 2026-09-28 defect, eight already-played fixtures on the card,
for the one section that got neither the gate nor the audit. It is held
today (the reviewed policy lists only the eight match markets) which is
exactly why it needs tests: nothing in production will exercise it until a
policy edit turns it on, and then all three runs a day rebuild it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.card_freshness import (
    PROPS_CARD_JSON,
    audit_card_freshness,
)
from epl_betting_lab.reports.player_props_card import drop_started_fixtures

KICKOFF = "2026-10-03T11:30:00+00:00"
BEFORE = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)
AFTER = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)


class TestTheAuditSeesProps:
    def _write(self, tmp_path: Path, *, generated: str, kickoff: str) -> None:
        (tmp_path / PROPS_CARD_JSON).write_text(
            json.dumps(
                {
                    "generated_at": generated,
                    "picks": [
                        {
                            "home_team": "Arsenal",
                            "away_team": "Chelsea",
                            "market": "player_shots",
                            "selection": "over",
                            "kickoff_time": kickoff,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_a_prop_that_already_kicked_off_is_a_fault(self, tmp_path: Path) -> None:
        self._write(
            tmp_path, generated="2026-10-03T14:00:00+00:00", kickoff=KICKOFF
        )
        verdict = audit_card_freshness(output_dir=tmp_path)

        assert verdict.fault_count == 1
        assert not verdict.clean
        assert PROPS_CARD_JSON in verdict.read

    def test_the_control_a_prop_before_kickoff_is_clean(self, tmp_path: Path) -> None:
        """Without this, an audit that flagged everything would pass above."""
        self._write(
            tmp_path, generated="2026-10-03T09:00:00+00:00", kickoff=KICKOFF
        )
        verdict = audit_card_freshness(output_dir=tmp_path)

        assert verdict.fault_count == 0
        assert verdict.checked == 1

    def test_a_prop_with_no_kickoff_is_unchecked_not_clean(
        self, tmp_path: Path
    ) -> None:
        """The distinction the verdict exists to make."""
        self._write(tmp_path, generated="2026-10-03T09:00:00+00:00", kickoff="")
        verdict = audit_card_freshness(output_dir=tmp_path)

        assert verdict.unchecked == 1
        assert verdict.checked == 0

    def test_a_props_card_with_no_generation_time_is_all_unchecked(
        self, tmp_path: Path
    ) -> None:
        """"Cannot be checked" must not round to "clean".

        The two other sections already say this in their own branches. Props
        lacked one, so a card written without a timestamp added nothing to
        either count and the verdict read clean over rows nobody had looked
        at — the precise shape the verdict exists to prevent.
        """
        (tmp_path / PROPS_CARD_JSON).write_text(
            json.dumps(
                {
                    "picks": [
                        {"home_team": "Arsenal", "away_team": "Chelsea",
                         "market": "player_shots", "selection": "over",
                         "kickoff_time": KICKOFF},
                        {"home_team": "Spurs", "away_team": "Everton",
                         "market": "player_shots", "selection": "under",
                         "kickoff_time": KICKOFF},
                    ]
                }
            ),
            encoding="utf-8",
        )
        verdict = audit_card_freshness(output_dir=tmp_path)

        assert verdict.unchecked == 2
        assert verdict.checked == 0
        assert PROPS_CARD_JSON in verdict.read

    def test_no_props_card_leaves_the_population_alone(self, tmp_path: Path) -> None:
        verdict = audit_card_freshness(output_dir=tmp_path)

        assert PROPS_CARD_JSON not in verdict.read
        assert verdict.checked == 0


class TestTheCardKeepsTheProvidersKickoff:
    """The gate, tested on its own.

    An earlier version of this asserted on `markets_with_staged_prices`,
    which is reported from RAW staging by the held-policy branch before
    anything is filtered — so it was reading a field the filter does not
    touch, and would have passed with the filter deleted.
    """

    def _frame(self, commence: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "date": "2026-10-03",
                    "commence_time": commence,
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "market": "player_shots_on_target",
                    "player": "Bukayo Saka",
                    "selection": "over",
                    "american_odds": "+120",
                    "book": "FanDuel",
                }
            ]
        )

    def test_a_fixture_already_kicked_off_is_dropped(self) -> None:
        """`"2026-10-03" >= "2026-10-03"` kept it all day."""
        assert drop_started_fixtures(self._frame(KICKOFF), AFTER).empty

    def test_the_control_the_same_fixture_survives_before_kickoff(self) -> None:
        assert len(drop_started_fixtures(self._frame(KICKOFF), BEFORE)) == 1

    def test_an_unreadable_kickoff_is_kept_not_silently_dropped(self) -> None:
        """Dropping a fixture because a column would not parse is worse."""
        assert len(drop_started_fixtures(self._frame("not a timestamp"), AFTER)) == 1

    def test_a_frame_without_the_column_is_untouched(self) -> None:
        """Staging files written before the column existed."""
        frame = self._frame(KICKOFF).drop(columns=["commence_time"])

        assert len(drop_started_fixtures(frame, AFTER)) == 1

    def test_the_builder_uses_it(self) -> None:
        """The producer being right is not the producer being called."""
        import inspect

        from epl_betting_lab.reports.player_props_card import build_player_props_card

        assert "drop_started_fixtures(" in inspect.getsource(build_player_props_card)

    def test_the_pick_records_the_kickoff(self) -> None:
        """`PropPick` had no kickoff field, so the record carried none."""
        from epl_betting_lab.reports.player_props_card import PropPick

        assert "kickoff_time" in PropPick.__dataclass_fields__
