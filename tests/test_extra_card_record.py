"""The Beyond-the-Premier-League selections have to be written down.

Until this existed they were rendered to markdown and posted in an issue
comment, and nowhere else. Prices for these competitions have been collected
since the EFL feed started; what was never kept is the record of what was
SELECTED, so closing-line value could not be computed for any of it, forwards
or backwards.

It matters most for the competition that needs it most. The international
section cannot be backtested — no free archive carries international prices —
so forward CLV is its only possible evidence. Without this record it could
never be shown to be good or bad, in either direction, ever.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.reports.extra_competitions_card import (
    EXTRA_ARCHIVE_ROOT,
    EXTRA_CARD_JSON_FILENAME,
    ExtraCard,
    extra_card_record,
    save_extra_card_record,
)

NOW = datetime(2026, 9, 23, 19, 21, 26, tzinfo=timezone.utc)

#: Everything a closing-line figure needs: which fixture, which bet, at what
#: price, with which book. Losing any one of them makes the row unscoreable.
REQUIRED = (
    "competition",
    "home_team",
    "away_team",
    "market",
    "selection",
    "american_odds",
    "book",
)


def _card(rows=1) -> ExtraCard:
    return ExtraCard(
        pd.DataFrame(
            [
                {
                    "home_team": "Italy",
                    "away_team": "Belgium",
                    "market": "draw_no_bet",
                    "selection": "away",
                    "american_odds": 135,
                    "book": "BetRivers",
                    "calibrated_edge": 0.067,
                    "raw_edge": 0.12,
                    "suggested_units": 0.1,
                }
                for _ in range(rows)
            ]
        ),
        [],
        priced=45,
        unrated=["Narnia v Utopia"],
    )


class TestTheRecordCarriesWhatScoringNeeds:
    def test_every_field_a_closing_line_figure_needs_is_present(self) -> None:
        record = extra_card_record({"UNL": _card()}, now=NOW)

        assert len(record["selections"]) == 1
        row = record["selections"][0]
        for field in REQUIRED:
            assert row.get(field) not in (None, ""), f"{field} is missing"

    def test_the_competition_is_on_every_row(self) -> None:
        """The feed these are scored against holds several competitions. A row
        that forgot which one it was could be matched to the wrong price."""
        record = extra_card_record({"UNL": _card(rows=2)}, now=NOW)

        assert {row["competition"] for row in record["selections"]} == {"UNL"}

    def test_the_declined_fixtures_and_priced_count_are_kept(self) -> None:
        """A quiet week and a coverage wall are different facts, and the record
        is the only place the difference survives the run."""
        record = extra_card_record({"UNL": _card()}, now=NOW)

        assert record["competitions"]["UNL"]["priced"] == 45
        assert record["competitions"]["UNL"]["declined"] == ["Narnia v Utopia"]


class TestARunThatSelectedNothingIsStillRecorded:
    def test_an_empty_card_still_writes_a_record(self, tmp_path: Path) -> None:
        """A gap in the archive cannot be told apart from a run that did not
        happen. A day with no selections is a fact about that day."""
        empty = ExtraCard(pd.DataFrame(), ["nothing cleared"], priced=12)

        record = save_extra_card_record({"UNL": empty}, output_dir=tmp_path, now=NOW)

        assert record["selections"] == []
        assert record["competitions"]["UNL"]["priced"] == 12
        assert (tmp_path / EXTRA_CARD_JSON_FILENAME).is_file()


class TestTheArchiveKeepsEveryRun:
    def test_the_archive_copy_is_timestamped_and_separate(self, tmp_path: Path) -> None:
        save_extra_card_record({"UNL": _card()}, output_dir=tmp_path, now=NOW)

        archived = tmp_path / EXTRA_ARCHIVE_ROOT / "2026-09-23" / "192126"
        assert (archived / EXTRA_CARD_JSON_FILENAME).is_file()
        assert (tmp_path / EXTRA_CARD_JSON_FILENAME).is_file()

    def test_a_second_run_does_not_overwrite_the_first(self, tmp_path: Path) -> None:
        """Four runs a day share a date. Keyed on the date alone, the last one
        would be the only one kept."""
        later = NOW.replace(hour=22, minute=30, second=5)

        save_extra_card_record({"UNL": _card()}, output_dir=tmp_path, now=NOW)
        save_extra_card_record({"UNL": _card(rows=2)}, output_dir=tmp_path, now=later)

        kept = sorted((tmp_path / EXTRA_ARCHIVE_ROOT / "2026-09-23").iterdir())
        assert [p.name for p in kept] == ["192126", "223005"]

    def test_the_archived_copy_matches_the_live_one(self, tmp_path: Path) -> None:
        save_extra_card_record({"UNL": _card()}, output_dir=tmp_path, now=NOW)

        live = json.loads((tmp_path / EXTRA_CARD_JSON_FILENAME).read_text())
        archived = json.loads(
            (
                tmp_path / EXTRA_ARCHIVE_ROOT / "2026-09-23" / "192126"
                / EXTRA_CARD_JSON_FILENAME
            ).read_text()
        )
        assert live == archived


class TestTheArchiveSurvivesBetweenRuns:
    def test_the_workflow_carries_the_archive_in_its_state_artifact(self) -> None:
        """Every runner is a fresh machine. An archive that is not in the state
        artifact is one run deep, which is the same as no archive: a
        closing-line figure needs the pick AND the later price, and the pick is
        the half that cannot be recovered afterwards.

        Asserted against the constant rather than a path typed here, so moving
        the archive without moving the upload fails.
        """
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")
        block = workflow.split("name: matchday-state", 1)[1].split(
            "if-no-files-found", 1
        )[0]

        assert f"data/outputs/{EXTRA_ARCHIVE_ROOT.as_posix()}" in block, (
            "the extra-card archive is not uploaded, so it lives for one run"
        )

    def test_the_build_script_calls_the_recorder(self) -> None:
        """Parsed, not grepped. `"save_extra_card_record" in script` is true of
        the import line alone, so it stayed green when the call itself was
        replaced — the same weakness that let a workflow ship a command that
        could never run, because a test asserted the text was present rather
        than that it worked.
        """
        import ast

        tree = ast.parse(
            (PROJECT_ROOT / "scripts" / "build_extra_card.py").read_text(
                encoding="utf-8"
            )
        )
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

        assert "save_extra_card_record" in called, (
            "the script imports the recorder without calling it, so nothing is "
            "written down"
        )
