"""The register of competitions asked for but not yet sold.

Written after one reading of the provider's sports list produced the claim that
the CONCACAF Nations League "is not sold at all". It was not being played — no
fixtures since March 2025 — and a listing cannot tell "not carried" from
"between editions". A competition APPEARING is unambiguous, and these tests are
about noticing that on the run that can.
"""

from __future__ import annotations

import importlib.util
import json
import re

import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.providers.competition_watch import (
    WANTED,
    WantedCompetition,
    find_wanted,
    render_watch,
)
from epl_betting_lab.providers.credential_check import (
    check_provider_credential,
    render_credential_check,
)
from epl_betting_lab.providers.odds_api_staging_provider import API_KEY_ENV

FAKE_KEY = "abcdef01" * 4

CNL = {"key": "soccer_concacaf_nations_league", "title": "CONCACAF Nations League", "active": True}
CNLQ = {
    "key": "soccer_concacaf_nations_league_qualification",
    "title": "CONCACAF Nations League Qualification",
    "active": False,
}
UNL = {"key": "soccer_uefa_nations_league", "title": "UEFA Nations League", "active": True}


def _collector():
    spec = importlib.util.spec_from_file_location(
        "collect_extra_competitions",
        PROJECT_ROOT / "scripts" / "collect_extra_competitions.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _only(*codes: str):
    """The register entries under test, so a test does not fail merely because
    another competition was registered. Pinning the whole register made three
    tests fail the moment a third entry was added, which is a test asserting
    the roster rather than the behaviour it names.
    """
    return tuple(want for want in WANTED if want.code in codes)


class TestNoticingThatSomethingArrived:
    def test_an_absent_competition_is_reported_with_the_reason(self) -> None:
        found = find_wanted([UNL], wanted=_only("CNL", "CNLQ"))

        assert [item["code"] for item in found["absent"]] == ["CNL", "CNLQ"]
        assert not found["available"]
        assert all(item["status"] for item in found["absent"])

    def test_an_arrival_is_announced_with_the_key_to_wire(self) -> None:
        """The whole point. The report has to carry the sport key, because the
        next step is writing it into SPORT_KEYS and prices cannot be recovered
        later."""
        lines = "\n".join(render_watch(find_wanted([UNL, CNL])))

        assert "now being sold" in lines
        assert "soccer_concacaf_nations_league" in lines

    def test_a_competition_already_collected_is_not_announced_again(self) -> None:
        lines = "\n".join(
            render_watch(find_wanted([CNL], collected={"soccer_concacaf_nations_league"}))
        )

        assert "now being sold" not in lines
        assert "Already collected" in lines


class TestTheQualifyingRoundIsNotTheCompetition:
    def test_qualification_alone_does_not_report_the_competition_as_available(
        self,
    ) -> None:
        """"concacaf.*nations league" matches "CONCACAF Nations League
        Qualification" as happily as the competition itself. A want-first loop
        announced the main competition the moment its qualifying round was
        listed — which is the one thing this register exists to get right."""
        found = find_wanted([CNLQ], wanted=_only("CNL", "CNLQ"))

        assert [item["code"] for item in found["available"]] == ["CNLQ"]
        assert [item["code"] for item in found["absent"]] == ["CNL"]

    def test_both_listed_resolve_to_one_entry_each(self) -> None:
        found = find_wanted([CNLQ, CNL], wanted=_only("CNL", "CNLQ"))

        assert sorted(item["code"] for item in found["available"]) == ["CNL", "CNLQ"]
        assert not found["absent"]
        by_code = {item["code"]: item["key"] for item in found["available"]}
        assert by_code["CNL"] == "soccer_concacaf_nations_league"
        assert by_code["CNLQ"] == "soccer_concacaf_nations_league_qualification"

    def test_another_confederations_nations_league_is_not_a_match(self) -> None:
        """UEFA's is already collected. Matching it here would report a
        competition as newly available every single run."""
        found = find_wanted([UNL])

        assert not found["available"]


class TestTheRegisterMeansWantedAndNotYetCollected:
    def test_nothing_wanted_is_already_being_collected(self) -> None:
        """Wiring a competition means removing it from the register. Without
        this the report announces an arrival on every run forever, which is how
        a signal becomes noise and then gets ignored."""
        keys = _collector().SPORT_KEYS.values()
        titles = {
            "CONCACAF Nations League",
            "UEFA Nations League",
            "UEFA Champions League",
            "EFL Cup",
        }

        for want in WANTED:
            for key in keys:
                assert not re.search(want.pattern, key, re.IGNORECASE), (
                    f"{want.name} is in the wanted register and also collected "
                    f"as {key}; remove it from the register"
                )
            # a title-level check too, since the register matches on titles
            for title in titles:
                if re.search(want.pattern, title, re.IGNORECASE):
                    assert want.code not in {"UNL"}, title

    def test_every_entry_says_why_it_is_not_wired(self) -> None:
        for want in WANTED:
            assert want.status.strip(), f"{want.code} has no status"
            assert len(want.status) > 40, (
                f"{want.code}'s status is too short to act on"
            )


class TestItCannotBreakTheCredentialCheck:
    @staticmethod
    def _report(body):
        class _Response:
            status_code = 200
            headers = {"x-requests-remaining": "1"}

            def json(self):
                return body

        return check_provider_credential(
            {API_KEY_ENV: FAKE_KEY}, requester=lambda url, **kw: _Response()
        )

    def test_the_watch_never_carries_the_credential(self) -> None:
        report = self._report([CNL, UNL])

        assert FAKE_KEY not in json.dumps(report)
        assert FAKE_KEY not in "\n".join(render_credential_check(report))

    @pytest.mark.parametrize("body", [[], "not a list", None], ids=["empty", "string", "none"])
    def test_an_unusable_listing_still_answers_the_credential_question(
        self, body
    ) -> None:
        """The watch is diagnostics riding on a credential check. It must never
        be the reason the check fails."""
        report = self._report(body)

        assert report["authenticated"] is True
        assert "Outcome" in "\n".join(
            line.split(":")[0] for line in render_credential_check(report)
        )


class TestMatchingIsByNameBecauseTheKeyIsUnknowable:
    def test_a_pattern_is_used_rather_than_a_sport_key(self) -> None:
        """The CONCACAF Nations League has never appeared in the listing, so it
        has no key to write down. A guessed key would match nothing and the
        register would stay silent forever."""
        for want in WANTED:
            assert not want.pattern.startswith("soccer_")

    def test_a_pattern_that_matches_nothing_is_still_reported(self) -> None:
        nonsense = (
            WantedCompetition(
                code="XXX", name="Invented Cup", pattern=r"no such competition",
                status="A status long enough to be actionable by a reader.",
            ),
        )
        found = find_wanted([UNL, CNL], wanted=nonsense)

        assert [item["code"] for item in found["absent"]] == ["XXX"]


class TestTheGoldCupCarriesItsMeasuredVerdict:
    """It is the one registered entry the provider actually sells. Measured
    2026-09-23: the tail screen passes better than the Nations League's, and
    the venue blocks it — 78% of its matches are neutral, the feed does not say
    which, and the card would shift the home side +9.4 points on every one.
    """

    @staticmethod
    def _entry():
        return next(want for want in WANTED if want.code == "GOLD")

    def test_it_is_registered_rather_than_wired(self) -> None:
        """Registered means the watch says when it comes into season; wired
        would mean collecting it. It is out of season either way."""
        assert self._entry() is not None
        keys = _collector().SPORT_KEYS.values()
        assert "soccer_concacaf_gold_cup" not in keys

    def test_the_status_says_collect_and_not_card(self) -> None:
        """A register entry whose status does not carry the verdict sends the
        next reader back to re-measure it."""
        status = self._entry().status.lower()

        assert "do not card" in status
        assert "neutral" in status, "the reason it is not carded is missing"

    def test_it_is_found_when_the_provider_lists_it(self) -> None:
        listing = [
            {
                "key": "soccer_concacaf_gold_cup",
                "title": "CONCACAF Gold Cup",
                "active": False,
            }
        ]

        found = find_wanted(listing, wanted=_only("GOLD"))

        assert [item["key"] for item in found["available"]] == [
            "soccer_concacaf_gold_cup"
        ]
        assert found["available"][0]["active"] is False
