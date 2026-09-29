"""Asking, from the output side, whether a stale selection shipped.

The 2026-09-28 card carried eight already-played fixtures. Two gates now stop
that. This checks the thing the gates are supposed to have achieved, and it does
not read their counts of what they dropped — a broken gate reports dropping
nothing, which is indistinguishable from a gate with nothing to drop.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.reports.card_freshness import (
    PLAYABLE_SECTIONS,
    audit_card_freshness,
    render_freshness,
)

GENERATED = "2026-09-28T18:17:00+00:00"


def _pl_card(**overrides) -> dict:
    card = {
        "generated_at": GENERATED,
        "best_bets": [
            {
                "home_team": "Arsenal",
                "away_team": "Leeds",
                "market": "btts",
                "selection": "yes",
                "kickoff_time": "2026-10-10T14:00:00+00:00",
            }
        ],
        "leans": [],
        "already_started": [],
        "quarantined": [],
    }
    card.update(overrides)
    return card


def _extra_card(**overrides) -> dict:
    card = {
        "generated_at": GENERATED,
        "selections": [
            {
                "competition": "UNL",
                "home_team": "Wales",
                "away_team": "Norway",
                "market": "double_chance",
                "selection": "home_or_draw",
                "kickoff_time": "2026-10-01T00:00:00+00:00",
            }
        ],
    }
    card.update(overrides)
    return card


def _write(tmp_path: Path, pl=None, extra=None) -> Path:
    if pl is not None:
        (tmp_path / "automated_card.json").write_text(json.dumps(pl), encoding="utf-8")
    if extra is not None:
        (tmp_path / "extra_competitions_card.json").write_text(
            json.dumps(extra), encoding="utf-8"
        )
    return tmp_path


class TestAStaleSelectionIsCaught:
    def test_a_clean_card_reports_no_fault(self, tmp_path: Path) -> None:
        verdict = audit_card_freshness(
            output_dir=_write(tmp_path, pl=_pl_card(), extra=_extra_card())
        )

        assert verdict.fault_count == 0
        assert verdict.clean is True
        assert verdict.checked == 2

    @pytest.mark.parametrize("which", ["pl", "extra"])
    def test_a_selection_that_kicked_off_first_is_a_fault(
        self, which, tmp_path: Path
    ) -> None:
        """Both sections are audited. The 2026-09-28 card was stale in the extra
        sections, but nothing about this check is specific to them."""
        pl, extra = _pl_card(), _extra_card()
        if which == "pl":
            pl["best_bets"][0]["kickoff_time"] = "2026-09-16T18:00:00+00:00"
        else:
            extra["selections"][0]["kickoff_time"] = "2026-09-16T18:00:00+00:00"

        verdict = audit_card_freshness(output_dir=_write(tmp_path, pl=pl, extra=extra))

        assert verdict.fault_count == 1
        assert verdict.clean is False
        assert "2026-09-16" in verdict.faults[0].kickoff

    def test_a_kickoff_exactly_at_generation_is_a_fault(self, tmp_path: Path) -> None:
        """At or before. A game kicking off the instant the card is written is
        not a play."""
        extra = _extra_card()
        extra["selections"][0]["kickoff_time"] = GENERATED

        verdict = audit_card_freshness(output_dir=_write(tmp_path, extra=extra))

        assert verdict.fault_count == 1

    def test_the_fault_names_the_fixture_and_both_times(self, tmp_path: Path) -> None:
        extra = _extra_card()
        extra["selections"][0]["kickoff_time"] = "2026-09-16T18:00:00+00:00"

        verdict = audit_card_freshness(output_dir=_write(tmp_path, extra=extra))
        text = "\n".join(render_freshness(verdict))

        assert "Wales v Norway" in text
        assert "2026-09-16" in text and "2026-09-28" in text


class TestWhatTheGateWithheldIsNotAudited:
    def test_a_started_fixture_in_the_quarantine_is_not_a_fault(
        self, tmp_path: Path
    ) -> None:
        """`already_started` is where the Premier League gate PUTS a started
        fixture. Counting it as a fault would report the gate working as the
        gate failing, and the check would be loudest exactly when it should be
        quiet."""
        pl = _pl_card(
            already_started=[
                {
                    "home_team": "Everton",
                    "away_team": "Wolves",
                    "market": "btts",
                    "selection": "no",
                    "kickoff_time": "2026-09-16T18:00:00+00:00",
                }
            ]
        )

        verdict = audit_card_freshness(output_dir=_write(tmp_path, pl=pl))

        assert verdict.fault_count == 0
        assert "already_started" not in PLAYABLE_SECTIONS


class TestAnUncheckableSelectionIsNotAPass:
    def test_a_selection_with_no_kickoff_is_counted_apart(self, tmp_path: Path) -> None:
        """Records written before kickoffs were captured have none. Folding
        those into a clean zero is how "nothing detected" comes to read as
        "nothing wrong"."""
        extra = _extra_card()
        extra["selections"][0].pop("kickoff_time")

        verdict = audit_card_freshness(output_dir=_write(tmp_path, extra=extra))

        assert verdict.unchecked == 1
        assert verdict.checked == 0
        assert verdict.fault_count == 0

    def test_a_card_with_no_generation_time_checks_nothing(self, tmp_path: Path) -> None:
        """Without it there is nothing to compare a kickoff against, and every
        row is unchecked rather than clean."""
        pl = _pl_card()
        pl.pop("generated_at")

        verdict = audit_card_freshness(output_dir=_write(tmp_path, pl=pl))

        assert verdict.checked == 0
        assert verdict.unchecked == 1

    def test_no_card_at_all_says_so(self, tmp_path: Path) -> None:
        verdict = audit_card_freshness(output_dir=tmp_path)

        assert verdict.read == []
        assert "no card to check" in " ".join(render_freshness(verdict))


class TestTheRunFailsLoudlyOnAFault:
    @staticmethod
    def _run(directory: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "check_card_freshness.py"),
                "--output-dir",
                str(directory),
            ],
            capture_output=True,
            text=True,
            env={
                **__import__("os").environ,
                "PYTHONPATH": str(PROJECT_ROOT / "src"),
            },
        )

    def test_a_clean_card_exits_zero_and_writes_the_report(self, tmp_path: Path) -> None:
        _write(tmp_path, pl=_pl_card(), extra=_extra_card())

        done = self._run(tmp_path)

        assert done.returncode == 0, done.stdout + done.stderr
        report = json.loads((tmp_path / "card_freshness.json").read_text())
        assert report["faults"] == 0 and report["clean"] is True

    def test_a_stale_selection_exits_non_zero(self, tmp_path: Path) -> None:
        """A run that shipped a stale pick must not pass quietly."""
        extra = _extra_card()
        extra["selections"][0]["kickoff_time"] = "2026-09-16T18:00:00+00:00"
        _write(tmp_path, pl=_pl_card(), extra=extra)

        done = self._run(tmp_path)

        assert done.returncode == 1
        assert "STALE" in done.stdout
        report = json.loads((tmp_path / "card_freshness.json").read_text())
        assert report["faults"] == 1 and report["clean"] is False


class TestTheVerdictReachesTheFeed:
    @staticmethod
    def _workflow() -> str:
        return (
            PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
        ).read_text(encoding="utf-8")

    def test_the_check_runs_before_the_card_is_published(self) -> None:
        """Published first and checked afterwards would put the verdict on the
        next card rather than this one."""
        import yaml

        spec = yaml.safe_load(self._workflow())
        job = next(iter(spec["jobs"].values()))
        names = [str(step.get("name", "")) for step in job["steps"]]
        checked = [i for i, name in enumerate(names) if "kicked off" in name]
        published = [i for i, name in enumerate(names) if "card-feed" in name]

        assert checked, "the workflow does not run the freshness check"
        assert published, "the publish step was renamed"
        assert checked[0] < published[0]

    def test_the_status_carries_the_verdict(self) -> None:
        """SOCCER WATCH reads `latest_status.json`. A verdict that stays in a
        run log is a verdict nobody reads.

        Asserted on the object jq BUILDS, not on the word appearing somewhere
        nearby: the `--argjson freshness` argument stays in place when the key
        is dropped from the output, so the looser check passed with the verdict
        never reaching the file.
        """
        workflow = self._workflow()
        built = workflow.split("' > card_status.json", 1)[0].rsplit("jq -n", 1)[-1]
        construction = built.split("'{date:", 1)[-1]

        assert "freshness: $freshness" in construction, (
            "the published status object does not include the freshness verdict"
        )
        assert "--argjson freshness" in built, "nothing computes it"
        assert "card_freshness.json" in built

    def test_a_missing_report_does_not_break_the_publish(self) -> None:
        """The check is continue-on-error, so the report can be absent. The
        publish step must still write a status."""
        workflow = self._workflow()

        assert 'echo \'{"checked":0,"unchecked":0,"faults":0,"clean":null}\'' in workflow


class TestTheKickoffIsFoundUnderTheNameTheCardUses:
    """The first production run of the freshness audit reported 0 faults and 3
    unchecked. All three were fixtures whose provider spelling differs from
    Football-Data's: "AS Roma" against "Roma", "Atletico Madrid" against
    "Ath Madrid", "Union Saint-Gilloise" against "St. Gilloise".

    `latest_prices` renames the teams; the kickoff lookup was keyed on the feed's
    raw names, so it missed exactly those. Gating was never wrong — that works on
    the feed's own names throughout — but the kickoff never reached the record,
    which is what the audit reads. A zero over unverified rows is the failure
    mode `unchecked` exists to expose, and it did.
    """

    @staticmethod
    def _feed(home: str, away: str, competition: str = "UCL") -> "pd.DataFrame":
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "competition": competition,
                    "commence_time": "2026-10-14T19:00:00Z",
                    "date": "2026-10-14",
                    "home_team": home,
                    "away_team": away,
                    "market": "btts",
                    "selection": selection,
                    "american_odds": 100,
                    "book": "DraftKings",
                    "observed_at": "2026-09-28T06:00:00Z",
                }
                for selection in ("yes", "no")
            ]
        )

    @pytest.mark.parametrize(
        "provider_spelling, card_spelling",
        [
            ("AS Roma", "Roma"),
            ("Atletico Madrid", "Ath Madrid"),
        ],
    )
    def test_a_renamed_club_still_resolves_to_its_kickoff(
        self, provider_spelling, card_spelling
    ) -> None:
        from epl_betting_lab.reports.extra_competitions_card import (
            _fixture_kickoffs,
            name_map_for,
        )

        rows = self._feed(provider_spelling, "Real Madrid")
        rename = name_map_for("UCL")
        renamed = rows.copy()
        renamed["home_team"] = renamed["home_team"].map(rename)
        renamed["away_team"] = renamed["away_team"].map(rename)

        kickoffs = _fixture_kickoffs(renamed)

        key = (card_spelling.casefold(), "real madrid")
        assert key in kickoffs, (
            f"the card calls this fixture {card_spelling}, and the kickoff map "
            f"has {sorted(kickoffs)} — it was built under the provider's name"
        )
        assert kickoffs[key] is not None

    def test_the_name_map_is_chosen_in_one_place(self) -> None:
        """The choice was made inside `latest_prices` and needed in two places.
        A second copy is how the two came to disagree."""
        from epl_betting_lab.data.european_clubs import provider_name
        from epl_betting_lab.data.international_teams import archive_name
        from epl_betting_lab.reports.extra_competitions_card import name_map_for

        assert name_map_for("UCL") is provider_name
        assert name_map_for("UNL") is archive_name


class TestTheCardRecordsTheKickoffItLookedUp:
    """`_fixture_kickoffs` resolving a renamed club and `build_extra_card`
    recording it are two different facts. Only the first was tested, so
    reverting the fix in the card left the suite green — the third time today
    that a producer was tested and its consumer was not.
    """

    def test_a_renamed_club_gets_a_kickoff_on_the_recorded_selection(
        self, monkeypatch
    ) -> None:
        import pandas as pd

        from epl_betting_lab.models.european_ratings import EUROPEAN_RATINGS
        from epl_betting_lab.reports import extra_competitions_card as card_module

        # A pool that knows the clubs by the names the CARD uses.
        history = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=7 * i),
                    "home_team": home,
                    "away_team": away,
                    "home_goals": hg,
                    "away_goals": ag,
                }
                for i in range(40)
                for home, away, hg, ag in (
                    ("Roma", "Real Madrid", 1, 1),
                    ("Real Madrid", "Roma", 2, 1),
                )
            ]
        )
        monkeypatch.setattr(
            card_module, "_pool_for", lambda spec: (history, EUROPEAN_RATINGS, None)
        )
        monkeypatch.setattr(
            card_module,
            "evaluate_btts",
            lambda projections, odds, *a, **k: pd.DataFrame(
                [
                    {
                        "home_team": "Roma",
                        "away_team": "Real Madrid",
                        "market": "btts",
                        "selection": "yes",
                        "american_odds": 120,
                        "book": "DraftKings",
                        "status": "BETTABLE",
                        "calibrated_edge": 0.09,
                        "raw_edge": 0.09,
                    }
                ]
            ),
        )

        # The feed names it the way the PROVIDER does.
        feed = pd.DataFrame(
            [
                {
                    "competition": "UCL",
                    "commence_time": "2026-10-14T19:00:00Z",
                    "date": "2026-10-14",
                    "home_team": "AS Roma",
                    "away_team": "Real Madrid",
                    "market": "btts",
                    "selection": selection,
                    "american_odds": 120,
                    "book": "DraftKings",
                    "observed_at": "2026-09-28T06:00:00Z",
                }
                for selection in ("yes", "no")
            ]
        )

        built = card_module.build_extra_card(
            feed, "UCL", now=pd.Timestamp("2026-09-28 18:17", tz="UTC")
        )

        assert not built.selections.empty, "the fixture did not reach the card at all"
        kickoff = built.selections.iloc[0]["kickoff_time"]
        assert kickoff, (
            "the selection was recorded with no kickoff, so the freshness audit "
            "cannot check it — the lookup used the provider's name and the card "
            "uses Football-Data's"
        )
