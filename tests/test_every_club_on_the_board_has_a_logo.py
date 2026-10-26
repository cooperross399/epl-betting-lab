"""Every club the board builder knows has a committed logo, and the board points at it.

The shared pages draw each team circle from `teams[abbr].logo` in board.json,
falling back to `./logos/<ABBR>.png` and then to the coloured abbreviation.
`web/fetch_logos.py` fills `web/logos/` once and the PNGs are committed; the
publish step copies web/ whole, so a file here is a file on the site.

"Every club the builder knows" is every abbreviation in `TEAMS`, including
the three relegated clubs kept for the settled record. The builder writes the
key only when the file exists, so a club with no logo carries no key rather
than a link to nothing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"


def _load(name: str, alias: str):
    spec = importlib.util.spec_from_file_location(alias, WEB / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = _load("build_board_json.py", "build_board_json_logos")
FETCH = _load("fetch_logos.py", "fetch_logos_under_test")
CLUBS = sorted(BUILDER.TEAMS.items())


def test_the_builder_knows_every_club_of_the_season_and_the_relegated_three() -> None:
    abbrs = {abbr for abbr, *_ in BUILDER.TEAMS.values()}
    assert len(abbrs) == len(BUILDER.TEAMS) == 23, abbrs


@pytest.mark.parametrize(("fd", "row"), CLUBS, ids=[fd for fd, _ in CLUBS])
def test_every_club_has_a_real_logo_file(fd: str, row: tuple) -> None:
    path = WEB / "logos" / f"{row[0]}.png"
    assert path.is_file(), f"{fd}: {path} is missing"
    problem = FETCH.png_problem(path.read_bytes(), FETCH.PUBLISHED_MIN_BYTES)
    assert problem is None, (fd, problem)
    assert FETCH.png_size(path.read_bytes()) == (FETCH.PUBLISHED_PX, FETCH.PUBLISHED_PX), fd


@pytest.mark.parametrize(("fd", "row"), CLUBS, ids=[fd for fd, _ in CLUBS])
def test_the_board_entry_points_at_an_existing_file(fd: str, row: tuple) -> None:
    abbr, entry = BUILDER.team_entry(fd)
    assert abbr == row[0]
    assert entry["logo"] == f"./logos/{abbr}.png"
    # Resolved the way the page resolves it: relative to the published web/.
    assert (WEB / entry["logo"]).resolve().is_file(), entry["logo"]


def test_a_club_with_no_file_carries_no_logo_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(BUILDER, "LOGOS", tmp_path)
    abbr, entry = BUILDER.team_entry("Arsenal")
    assert abbr == "ARS" and "logo" not in entry, entry


def test_every_file_is_sourced_and_marked_as_a_trademark() -> None:
    text = (WEB / "logos" / "SOURCES.md").read_text(encoding="utf-8")
    assert "trademarks, shown for identification only" in text
    for png in sorted((WEB / "logos").glob("*.png")):
        line = next((ln for ln in text.splitlines() if f"`{png.name}`" in ln), "")
        assert "https://" in line, f"{png.name} has no source URL in SOURCES.md"


def test_the_validator_refuses_what_is_not_a_png() -> None:
    real = (WEB / "logos" / "ARS.png").read_bytes()
    assert FETCH.png_problem(b"<html>" + b" " * 4096) == "not a PNG signature"
    assert FETCH.png_problem(real[:1000]) is not None
    assert FETCH.png_problem(real[:-40] + b"\x00" * 40) is not None
