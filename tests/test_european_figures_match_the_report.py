"""The card quotes measurements. They have to be the current ones.

The Champions League note shipped "701 European ties bridge eleven leagues —
8.5% better than a league-average prior", with an interval of -0.161 to
-0.092. The generated report said 868 ties, +7.45%, and -0.1387 to -0.0798.

701 was not a typo and not a rounding: it is the Champions League's OWN
resolved share of the bridge, and it WAS the whole bridge while the Champions
League was the only competition on it. Adding the Europa League (143) and the
Conference League (24) took the bridge to 868, and four restatements did not
move — one of them inside the report generator, which printed a computed 868
in its summary and a typed 701 twelve paragraphs later. The document
contradicted itself and nothing noticed.

These tests pin the figures to the file that generates them, and check the one
arithmetic relation that would have caught it on day one.
"""

from __future__ import annotations

import re

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.models.european_ratings import (
    BRIDGE_DOMESTIC_MATCHES,
    BRIDGE_IMPROVEMENT_PCT,
    BRIDGE_INTERVAL,
    BRIDGE_TIES,
    CHAMPIONS_LEAGUE_TIES,
    CONFERENCE_LEAGUE_TIES,
    EUROPA_LEAGUE_TIES,
)
from epl_betting_lab.reports.extra_competitions_card import COMPETITIONS

REPORT = OUTPUTS_DIR / "european_ratings.md"


def _report() -> str:
    return REPORT.read_text(encoding="utf-8")


def test_the_shares_sum_to_the_bridge() -> None:
    """The one line that would have caught it: 701 + 143 + 24 = 868, not 701.

    A competition's own share and the whole bridge are different quantities
    that were the same number once. Nothing related them, so when they stopped
    being equal nothing said so.
    """
    assert (
        CHAMPIONS_LEAGUE_TIES + EUROPA_LEAGUE_TIES + CONFERENCE_LEAGUE_TIES
        == BRIDGE_TIES
    )


def test_the_tie_count_matches_the_generated_report() -> None:
    found = re.search(r"\*\*([\d,]+) European ties\*\*", _report())

    assert found, "the report no longer states a tie count in the form pinned here"
    assert int(found.group(1).replace(",", "")) == BRIDGE_TIES


def test_the_domestic_count_matches_the_generated_report() -> None:
    found = re.search(r"\*\*([\d,]+) domestic matches\*\*", _report())

    assert found
    assert int(found.group(1).replace(",", "")) == BRIDGE_DOMESTIC_MATCHES


def test_the_improvement_and_its_interval_match_the_generated_report() -> None:
    """The interval too. It was quoted 17% wider than the measurement."""
    report = _report()
    improvement = re.search(r"\*\*\+([\d.]+)%\*\*", report)
    interval = re.search(r"\*\*([-\d.]+) to ([-\d.]+)\*\*", report)

    assert improvement and interval
    assert float(improvement.group(1)) == BRIDGE_IMPROVEMENT_PCT
    assert (float(interval.group(1)), float(interval.group(2))) == BRIDGE_INTERVAL


def test_the_champions_league_note_quotes_the_bridge_not_one_share() -> None:
    """The defect, stated as the thing that must not come back."""
    note = COMPETITIONS["UCL"].note

    assert f"{BRIDGE_TIES} European ties" in note
    assert f"{BRIDGE_IMPROVEMENT_PCT}%" in note
    assert f"{CHAMPIONS_LEAGUE_TIES} European ties" not in note, (
        "that is the Champions League's own share, not the bridge"
    )


def test_the_conference_league_note_compares_like_with_like() -> None:
    """701 is correct here — both are resolved counts — so it is kept and said.

    Written down because the obvious "fix" is to replace it with 868, which
    would make a true sentence false.
    """
    note = COMPETITIONS["UECL"].note

    assert f"{CONFERENCE_LEAGUE_TIES} Conference League ties" in note
    assert str(CHAMPIONS_LEAGUE_TIES) in note
    assert "both resolved counts" in note


def test_the_generator_no_longer_types_a_tie_count_into_its_prose() -> None:
    """It printed a computed figure and a typed one in the same document."""
    source = (PROJECT_ROOT / "scripts" / "european_ratings_report.py").read_text(
        encoding="utf-8"
    )
    prose = [
        line
        for line in source.splitlines()
        if "European ties correct that only" in line
    ]

    assert prose, "the paragraph that carried the typed figure is gone; re-pin this"
    assert "pool.ties" in "\n".join(prose), (
        "the tie count in that sentence has to be interpolated, not typed"
    )


def test_the_report_does_not_contradict_itself() -> None:
    """Both mentions of the tie count, not just the one the generator writes.

    The generator was fixed to interpolate `pool.ties` and the COMMITTED
    report was left alone, so `european_ratings.md` went on saying 868 in
    its summary line and 701 twelve paragraphs down — the exact
    self-contradiction the change was supposed to remove, still sitting in
    the artifact a reader opens.

    Pinning the constants to the report cannot catch this: it reads the
    first match and stops.
    """
    counts = {
        int(found.replace(",", ""))
        for found in re.findall(r"([\d,]+) European ties", _report())
    }

    assert counts == {BRIDGE_TIES}, (
        f"the report states {sorted(counts)} European ties in different places"
    )
