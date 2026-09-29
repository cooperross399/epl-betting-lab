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


#: The one market with no historical price anywhere. Every other market the
#: card stakes is scored in `derived_market_backtest.md`.
UNMEASURABLE = "corners_1x2"

#: How a document says it is quoting a claim it has retired rather than
#: making one. A retraction has to repeat the sentence it retracts, so it
#: needs a marker; one agreed marker beats a regex that grows a clause every
#: time somebody phrases a correction differently.
RETRACTED = ("Correction, ", "when this was written", "until 2026-")


def test_cannot_be_profit_backtested_is_only_ever_said_of_one_market() -> None:
    """It was said of the whole card, of BTTS, and of every corner rule.

    All three stopped being true when the per-event history was bought. The
    card's own staking note told the reader "none of them can be
    profit-backtested" while six of its markets sit in the generated report
    with bets and intervals — a false reason for a correct stake, which is
    the kind of sentence that gets quoted back.

    Scoped rather than banned: the claim is still true of `corners_1x2`, so
    the test requires the market to be named near it rather than requiring
    the phrase to disappear.
    """
    from pathlib import Path

    claim = "profit-backtest"
    offenders = []
    for path in sorted((PROJECT_ROOT / "src").rglob("*.py")) + sorted(
        (PROJECT_ROOT / "docs").rglob("*.md")
    ):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines()):
            if claim not in line:
                continue
            # The sentence may wrap, so read a small window around it —
            # for the NEGATION as well as for the retraction marker. Reading
            # the negation from `line` alone missed
            # `models/poisson_goals.py`, where "no bet rule on it can ever be"
            # ends one line and "profit-backtested" begins the next. A guard
            # that only sees one line cannot see a wrapped sentence, which is
            # how most of these are written.
            lines = text.splitlines()
            window = "\n".join(lines[max(0, i - 3): i + 4])
            before = " ".join(lines[max(0, i - 2): i + 1]).lower()
            negated = any(
                word in before
                for word in ("cannot", "can never", "no ", "none")
            )
            # A retraction necessarily quotes the claim it retracts, so it
            # needs a way to say so. One agreed marker, not a growing list
            # of spellings: a window carrying RETRACTED is a correction.
            retracted = any(marker in window for marker in RETRACTED)
            if negated and UNMEASURABLE not in window and not retracted:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{i + 1}")

    assert not offenders, (
        "these say a market cannot be profit-backtested without naming "
        f"{UNMEASURABLE}, the only one for which that is still true: {offenders}"
    )


def test_the_control_the_unmeasurable_market_is_still_called_out() -> None:
    """A test that passes because the phrase vanished proves nothing."""
    corners = (
        PROJECT_ROOT / "src" / "epl_betting_lab" / "reports" / "count_calibration.py"
    ).read_text(encoding="utf-8")

    assert UNMEASURABLE in corners
    assert "profit-backtest" in corners


def test_the_prose_reading_the_table_agrees_with_the_table() -> None:
    """The rewrite corrected the tables and left the paragraphs behind.

    `every_market_measured.md` went on saying "Draw-no-bet's +13.0% is
    thirteen bets" twenty-four lines under a table reading 68 bets at
    +8.24%, and "Double chance is the only negative point estimate" under a
    table with two negatives — the worse of them corners. CLAUDE.md carried
    the thirteen-bet claim too.

    Stated as what the prose MUST say, not as what it must not. Banning the
    old phrases cannot work here: a retraction has to quote them, and it
    sits directly beside the sentence it corrects, so any exemption window
    wide enough for the retraction also covers a regression.
    """
    generated = _generated()

    # Counted over the DOC'S OWN TABLE, not over BOUGHT. BOUGHT exists to
    # pin the five book-filtered markets to the generated report, and
    # `derived_market_backtest.md` has no `total_2_5` or `1x2` row at all —
    # so counting negatives over it missed `total_2_5` at −10.8% and the
    # guard demanded the sentence "two point estimates are negative" that
    # its own table contradicts. A roster only guards what it names.
    table = _doc_rows(
        _ascii(MEASURED.read_text(encoding="utf-8")).split(
            "### What the best-price-across-books harvest said"
        )[0]
    )
    negatives = sorted(m for m, row in table.items() if row["roi"] < 0)

    assert len(negatives) >= 2, f"the table's negatives changed: {negatives}"
    for market in BOUGHT:
        if generated[market]["roi"] < 0:
            assert market in negatives, (
                f"{market} is negative in the generated report and not in "
                "the doc table"
            )

    dnb = generated["draw_no_bet"]
    for path in (MEASURED, CLAUDE):
        text = _ascii(path.read_text(encoding="utf-8"))
        assert f"{dnb['roi']}% on {int(dnb['bets'])} bets" in text, (
            f"{path.name} does not state draw_no_bet as "
            f"{dnb['roi']}% on {int(dnb['bets'])} bets"
        )

    measured = _ascii(MEASURED.read_text(encoding="utf-8"))
    hides = measured.split("## What the headline numbers hide")[1]
    for market in negatives:
        assert market in hides, (
            f"the interpretation does not name {market}, which the table "
            "scores negative"
        )

    # And the heading has to carry the COUNT. Naming both markets in the
    # body is not enough: a heading reading "Double chance is the only
    # negative point estimate" sat above a body that named corners too, and
    # the heading is what a reader takes away. Generated from the table, so
    # a third negative market breaks it rather than passing quietly.
    words = {1: "One point estimate is", 2: "Two point estimates are",
             3: "Three point estimates are", 4: "Four point estimates are"}
    assert f"{words[len(negatives)]} negative" in hides, (
        f"the section does not head with {len(negatives)} negative estimates: "
        f"{negatives}"
    )
    # And the same count on the card, which prints it to the reader. The
    # card's note wraps across string literals, so the source is flattened
    # before searching — an `or` across two spellings would pass on either.
    card = " ".join(
        (PROJECT_ROOT / "src" / "epl_betting_lab" / "reports" / "automated_card.py")
        .read_text(encoding="utf-8")
        .split()
    ).replace('" "', "")
    spelled = words[len(negatives)].split()[0].lower()
    assert f"{spelled} point estimates are negative" in card, (
        f"the card's staking note does not say {spelled} point estimates "
        "are negative"
    )


def test_the_control_the_retraction_may_still_quote_the_old_claim() -> None:
    """A correction has to repeat what it corrects, or it explains nothing."""
    text = _ascii(MEASURED.read_text(encoding="utf-8"))

    assert "thirteen bets" in text, (
        "the retraction should name the figure it retires, not silently drop it"
    )
