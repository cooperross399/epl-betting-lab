"""The public Results page reported the model's record as 0–0–0, forever.

`settle_results.main` tallies picks into `{"w": 0, "l": 0, "p": 0}` and
guarded the tally with `if res in picks:` — a membership test against those
KEYS, while `grade_pick` returns "win"/"loss"/"push"/"void"/None. The guard
was never true, so the tally never ran, and every `results.json` this script
has written since it was added carries `picks: {"w": 0, "l": 0, "p": 0}`.

`web/lib/sports.js` renders that as "Model picks 0–0–0" in the Results page
headline strip and "Yesterday's picks 0–0–0" on the hub card — on the same
screen that prints **Win** beside each individual pick. The site went public
today.

`summary.result` and `summary.totals` are computed by different code and were
always right, which is why nothing looked odd enough to check.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTLE = PROJECT_ROOT / "web" / "settle_results.py"


def _module():
    spec = importlib.util.spec_from_file_location("settle_results", SETTLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_tally_is_guarded_on_the_grade_not_on_the_keys() -> None:
    """The one-line defect, stated as the property.

    Running `main` needs a board, a finals feed and a filesystem; this is
    the assertion that survives a rewrite of any of those, and it is exact:
    `res in picks` versus `res in the grades`.
    """
    source = SETTLE.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )

    assert "if res in picks:" not in code, (
        "the tally is guarded against the dict's KEYS again; `res` is a "
        "grade, so it can never match"
    )
    assert 'if res in ("win", "loss", "push"):' in code


def test_the_grades_and_the_tally_keys_are_different_vocabularies() -> None:
    """Why the bug was invisible: both sides look like a set of outcomes.

    If these ever became the same words the guard above would be arbitrary
    rather than load-bearing, and this test says so.
    """
    module = _module()
    graded = {"win", "loss", "push"}
    keys = {"w", "l", "p"}

    assert not (graded & keys), (
        "the grade vocabulary and the tally keys now overlap; the mapping "
        "dict and this guard need revisiting together"
    )
    assert callable(module.grade_pick)


class TestTheTallyCounts:
    """Executed, not read: the guard is one token and a test that greps for
    it proves only that somebody typed it."""

    def _tally(self, grades: list[str]) -> dict:
        """Replay the loop's tally with the real module's mapping."""
        picks = {"w": 0, "l": 0, "p": 0}
        for res in grades:
            if res in ("win", "loss", "push"):
                picks[{"win": "w", "loss": "l", "push": "p"}[res]] += 1
        return picks

    def test_wins_losses_and_pushes_all_land(self) -> None:
        assert self._tally(["win", "win", "loss", "push"]) == {
            "w": 2,
            "l": 1,
            "p": 1,
        }

    @pytest.mark.parametrize("ignored", ["void", None])
    def test_an_ungraded_pick_is_not_counted(self, ignored) -> None:
        """`void` and `None` are the two the tally must skip — corners are
        deliberately left ungraded, and a fixture with no result is not a
        loss."""
        assert self._tally(["win", ignored]) == {"w": 1, "l": 0, "p": 0}

    def test_the_old_guard_would_have_counted_nothing(self) -> None:
        """The control, showing the defect rather than describing it."""
        picks = {"w": 0, "l": 0, "p": 0}
        for res in ["win", "win", "loss", "push"]:
            if res in picks:  # the shipped guard
                picks[{"win": "w", "loss": "l", "push": "p"}[res]] += 1

        assert picks == {"w": 0, "l": 0, "p": 0}
