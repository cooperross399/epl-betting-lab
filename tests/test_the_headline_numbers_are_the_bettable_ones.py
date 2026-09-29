"""The answer to "does it work?" has to be the measurement that still stands.

`docs/every_market_measured.md` said, in its own header, that the bought
markets were "priced three hours before each kick-off at the best price
across books". That is the method the repo later ruled unusable — a maximum
over books Cooper cannot bet is optimistic by construction — and the
generated report dropped those rows. The docs kept the numbers.

So CLAUDE.md, which is the first file a session reads and which tells it to
answer "whether it works" from these documents, carried BTTS at +15.0% over
51 bets when the bettable-books measurement is +0.66% over 31. Four of the
five bought markets were flattered; `corners_total_10_5` went from +1.7% to
−18.8%.

These tests read the generated report and require the prose to match it.
"""

from __future__ import annotations

import re

from epl_betting_lab.config import OUTPUTS_DIR, PROJECT_ROOT

REPORT = OUTPUTS_DIR / "derived_market_backtest.md"
MEASURED = PROJECT_ROOT / "docs" / "every_market_measured.md"
CLAIMS = PROJECT_ROOT / "docs" / "what_we_can_and_cannot_claim.md"
CLAUDE = PROJECT_ROOT / "CLAUDE.md"

#: Markets whose prices were bought and are scored in the generated report.
#: `1x2` and `total_2_5` come from Football-Data and are not affected by the
#: book filter, so they are not pinned here.
BOUGHT = ("btts", "corners_total_10_5", "corners_total_9_5", "double_chance", "draw_no_bet")


def _generated() -> dict[str, dict[str, float]]:
    """The report's own table, parsed."""
    rows: dict[str, dict[str, float]] = {}
    for line in REPORT.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 8 or cells[0] in ("market", ":-------------------"):
            continue
        if not re.fullmatch(r"[a-z0-9_]+|ALL", cells[0]):
            continue
        try:
            rows[cells[0]] = {"bets": float(cells[1]), "roi": float(cells[5])}
        except ValueError:
            continue
    return rows


def test_the_report_still_has_the_shape_these_tests_read() -> None:
    """The control for every test below: a parse that silently returns
    nothing would make all of them vacuous."""
    generated = _generated()

    assert set(BOUGHT) <= set(generated)
    assert "ALL" in generated


def _ascii(text: str) -> str:
    """The docs use a typographic minus; the generated report uses a hyphen.

    Comparing the two as strings made this test fail on punctuation, which
    is not the property being checked.
    """
    return text.replace("\u2212", "-")


def _doc_rows(text: str) -> dict[str, dict[str, float]]:
    """Market rows out of a docs table, by backticked market name."""
    rows: dict[str, dict[str, float]] = {}
    for line in _ascii(text).splitlines():
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) < 5 or not cells[0].startswith("`"):
            continue
        name = cells[0].strip("`")
        try:
            rows[name] = {"bets": float(cells[1]), "roi": float(cells[3].rstrip("%"))}
        except ValueError:
            continue
    return rows


def test_every_bought_market_is_quoted_at_its_measured_roi() -> None:
    generated = _generated()
    # Only the current table; the superseded figures are kept below it on
    # purpose, so the search stops where that section begins.
    current = MEASURED.read_text(encoding="utf-8").split(
        "### What the best-price-across-books harvest said"
    )[0]
    stated = _doc_rows(current)

    assert set(BOUGHT) <= set(stated), (
        f"markets missing from the doc table: {sorted(set(BOUGHT) - set(stated))}"
    )
    for market in BOUGHT:
        assert stated[market]["bets"] == generated[market]["bets"], market
        assert abs(stated[market]["roi"] - generated[market]["roi"]) < 0.01, (
            f"{market}: doc says {stated[market]['roi']}, "
            f"the report says {generated[market]['roi']}"
        )


def test_the_headline_btts_figure_is_the_bettable_one() -> None:
    """The number a session is told to answer "does it work?" with."""
    generated = _generated()["btts"]

    for path in (CLAIMS, CLAUDE):
        text = _ascii(path.read_text(encoding="utf-8"))
        assert f"{generated['roi']}% over {int(generated['bets'])} bets" in text or (
            f"| {int(generated['bets'])} |" in text
        ), f"{path.name} does not carry the measured BTTS figure"
        # It may still be NAMED as the superseded figure — that is the record
        # of the correction — but not offered as the current one.
        current_claim = text.split("read +15.0%")[0].split("row read 51 bets")[0]
        assert "+15.0%" not in current_claim, (
            f"{path.name} still quotes the best-price-across-books harvest "
            "as a current figure"
        )


def test_the_pooled_result_is_stated_and_is_not_hidden() -> None:
    """A loss across every bought market together is the honest summary."""
    pooled = _generated()["ALL"]

    for path in (MEASURED, CLAIMS):
        text = _ascii(path.read_text(encoding="utf-8"))
        assert str(int(pooled["bets"])) in text
        assert f"{pooled['roi']}%" in text, f"{path.name} omits the pooled ROI"


def test_only_the_market_with_no_history_is_called_unmeasurable() -> None:
    """Three markets were named unmeasurable after being bought and scored."""
    section = CLAIMS.read_text(encoding="utf-8").split("## What cannot be measured at all")[1]
    section = section.split("## ")[0]

    assert "corners_1x2" in section
    for market in ("double chance", "draw-no-bet"):
        assert f"{market} have no historical prices" not in section
    for market in BOUGHT:
        assert market in _generated(), "a market called unmeasurable is scored"
