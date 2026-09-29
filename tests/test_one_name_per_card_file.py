"""Each card's filename is written once.

There were thirteen literals across seven modules, and two of them collided:
`CARD_JSON_FILENAME` meant `automated_card.json` in `automated_card.py` and
`card_history.py`, and `player_props_card.json` in `player_props_card.py`.
An import of the wrong one would have type-checked, run, and audited the
wrong card — the kind of fault that produces a clean verdict about a file
nobody meant to check.

Three of them already drifted apart in ways that cost something this week:
`card_freshness` kept its own spelling of the Beyond record and was the only
reader of it, and the props card's name existed in four places while no audit
opened any of them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from epl_betting_lab.config import (
    AUTOMATED_CARD_JSON,
    EXTRA_CARD_JSON,
    PROPS_CARD_JSON,
    PROJECT_ROOT,
)

FILENAMES = (AUTOMATED_CARD_JSON, EXTRA_CARD_JSON, PROPS_CARD_JSON)
CONFIG = PROJECT_ROOT / "src" / "epl_betting_lab" / "config.py"
SOURCES = sorted((PROJECT_ROOT / "src").rglob("*.py")) + sorted(
    (PROJECT_ROOT / "scripts").rglob("*.py")
)


def _string_literals(path: Path) -> set[str]:
    """Every string constant in a module, via the parser.

    Not a grep: the comment in `config.py` explaining this rule contains all
    three filenames, and a grep would flag the explanation.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


@pytest.mark.parametrize("filename", FILENAMES)
def test_no_module_spells_a_card_filename_for_itself(filename: str) -> None:
    offenders = [
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in SOURCES
        if path != CONFIG and filename in _string_literals(path)
    ]

    assert not offenders, (
        f"{filename!r} is written out in {offenders}; import it from "
        "epl_betting_lab.config instead"
    )


#: The filenames themselves, written out HERE and nowhere else in the tree.
#:
#: A test may name the value it is checking; that is what makes it a check.
#: The first version of this compared `AUTOMATED_CARD_JSON` against the
#: literals in `config.py` — both sides of which move together, so changing
#: the constant to "other.json" passed. A pin has to come from outside the
#: thing it pins.
EXPECTED = {
    "AUTOMATED_CARD_JSON": "automated_card.json",
    "EXTRA_CARD_JSON": "extra_competitions_card.json",
    "PROPS_CARD_JSON": "player_props_card.json",
}


def test_the_names_are_the_files_the_pipeline_actually_writes() -> None:
    """Renaming one of these silently orphans every reader of that card."""
    from epl_betting_lab import config

    for name, filename in EXPECTED.items():
        assert getattr(config, name) == filename


def test_config_actually_holds_them() -> None:
    """The control. Otherwise deleting all three would pass the scan above."""
    literals = _string_literals(CONFIG)

    for filename in EXPECTED.values():
        assert filename in literals


def test_the_three_names_are_three_different_files() -> None:
    assert len(set(FILENAMES)) == 3


def test_the_colliding_alias_still_means_what_each_module_needs() -> None:
    """`CARD_JSON_FILENAME` is two different files in two modules.

    Kept, because renaming it reaches further than this change should, and
    pinned, because the collision is the reason the consolidation matters:
    both spellings are now derived, so neither can drift, but a future edit
    could still point one of them at the wrong constant.
    """
    from epl_betting_lab.reports.automated_card import (
        CARD_JSON_FILENAME as CARD,
    )
    from epl_betting_lab.reports.card_history import (
        CARD_JSON_FILENAME as HISTORY,
    )
    from epl_betting_lab.reports.player_props_card import (
        CARD_JSON_FILENAME as PROPS,
    )

    assert CARD == HISTORY == AUTOMATED_CARD_JSON
    assert PROPS == PROPS_CARD_JSON
    assert PROPS != CARD, "the collision that made this worth doing"


def test_every_alias_resolves_to_the_shared_constant() -> None:
    """The names modules kept for their own readers."""
    from epl_betting_lab.reports.card_freshness import (
        CARD_JSON,
        EXTRA_CARD_JSON as FRESHNESS_EXTRA,
        PROPS_CARD_JSON as FRESHNESS_PROPS,
    )
    from epl_betting_lab.reports.extra_competitions_card import (
        EXTRA_CARD_JSON_FILENAME,
    )

    assert CARD_JSON == AUTOMATED_CARD_JSON
    assert FRESHNESS_EXTRA == EXTRA_CARD_JSON
    assert FRESHNESS_PROPS == PROPS_CARD_JSON
    assert EXTRA_CARD_JSON_FILENAME == EXTRA_CARD_JSON
