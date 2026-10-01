"""The Results page published an ungraded pick as a Push, and hid how many there were.

`resultPick` in `web/lib/sports.js` mapped every result it did not recognise
-- `null`, a missing key, any word other than win, loss or void -- to "Push",
the word for a returned stake. A pick the settler could not answer for was
published as one that was answered and refunded. And the results strip printed
`summary.picks` as "Model picks 0-0-0" without `summary.ungraded`, which the
settler writes beside it, so a page whose every pick was ungraded read exactly
like a page with nothing to grade.

`web/lib/sports.js` is shared byte-identical by the EPL, NHL and CBB labs and
the hub, so this test renders all three sports' Results adapters through the
page's own code under node, and is carried by each lab.

The fix: only `result: "push"` is a Push. Anything else is "Not graded", in the
neutral colours an unpriced game already uses, and the Model picks cell names
the ungraded count when there is one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
SPORTS = ("nhl", "epl", "cbb")

_DRIVER = r"""
import { readFileSync } from "node:fs";
import { ADAPTERS } from "./lib/sports.js";
const [sport, dataPath] = process.argv.slice(2);
const data = JSON.parse(readFileSync(dataPath, "utf8"));
process.stdout.write(JSON.stringify(ADAPTERS[sport].results(data)));
"""


def _render(sport: str, payload: dict, tmp_path: Path) -> dict:
    node = shutil.which("node")
    assert node, (
        "node is not on PATH. This test renders the page's own adapter, which "
        "is the half of the site that prints the word a visitor reads."
    )
    site = tmp_path / f"site-{sport}"
    (site / "lib").mkdir(parents=True, exist_ok=True)
    for name in ("sports.js", "format.js"):
        shutil.copyfile(WEB / "lib" / name, site / "lib" / name)
    # node reads a bare `.js` as CommonJS on the versions runners carry.
    (site / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (site / "render.mjs").write_text(_DRIVER, encoding="utf-8")
    data = site / "results.json"
    data.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [node, str(site / "render.mjs"), sport, str(data)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, f"the {sport} results adapter threw:\n{result.stderr}"
    return json.loads(result.stdout)


def _game(pick: dict | None) -> dict:
    side = lambda abbr, final: {"abbr": abbr, "final": final, "projGoals": 1.2, "projPts": 70.0}  # noqa: E731
    return {"away": side("AAA", 2), "home": side("BBB", 1), "projWinner": "AAA",
            "projResult": "away", "markets": {}, "pick": pick}


def _results(picks: list[dict], ungraded: int | None) -> dict:
    summary: dict = {"picks": {"w": 0, "l": 0, "p": 0}}
    if ungraded is not None:
        summary["ungraded"] = ungraded
    return {"season": "2026-27", "summary": summary, "games": [_game(p) for p in picks]}


def _pick(result) -> dict:
    pick = {"label": "Under 10.5 corners", "market": "Corners 10.5", "price": -110}
    if result is not _MISSING:
        pick["result"] = result
    return pick


_MISSING = object()


@pytest.mark.parametrize("sport", SPORTS)
@pytest.mark.parametrize("result", [None, _MISSING, "pending", ""], ids=["null", "absent", "unknown", "empty"])
def test_an_unrecognised_result_is_not_published_as_a_push(sport, result, tmp_path) -> None:
    rendered = _render(sport, _results([_pick(result)], ungraded=1), tmp_path)
    pick = rendered["games"][0]["pick"]
    assert pick["result"] != "Push", (
        f"{sport}: a pick the settler could not grade is published as a "
        "returned stake"
    )
    assert pick["result"] == "Not graded"


@pytest.mark.parametrize("sport", SPORTS)
@pytest.mark.parametrize("result, word", [("win", "Win"), ("loss", "Loss"), ("void", "Void"), ("push", "Push")])
def test_a_graded_pick_keeps_its_word(sport, result, word, tmp_path) -> None:
    rendered = _render(sport, _results([_pick(result)], ungraded=0), tmp_path)
    assert rendered["games"][0]["pick"]["result"] == word


def _picks_cell(rendered: dict) -> dict:
    cells = [c for c in rendered["strip"] if c["label"].startswith("Model picks")]
    assert len(cells) == 1, rendered["strip"]
    return cells[0]


@pytest.mark.parametrize("sport", SPORTS)
def test_the_strip_names_the_ungraded_picks(sport, tmp_path) -> None:
    rendered = _render(sport, _results([_pick(None), _pick(None)], ungraded=2), tmp_path)
    cell = _picks_cell(rendered)
    assert "2 ungraded" in cell["label"], (
        f"{sport}: Model picks reads {cell['value']} with two picks ungraded "
        "and says nothing about them"
    )


@pytest.mark.parametrize("sport", SPORTS)
@pytest.mark.parametrize("ungraded", [0, None], ids=["zero", "unreported"])
def test_the_strip_is_unchanged_when_nothing_is_ungraded(sport, ungraded, tmp_path) -> None:
    rendered = _render(sport, _results([_pick("win")], ungraded=ungraded), tmp_path)
    assert _picks_cell(rendered)["label"] == "Model picks"
