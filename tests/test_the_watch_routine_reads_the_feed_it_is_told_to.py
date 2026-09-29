"""The weekly routine was half-converted from email to the card feed.

Delivery moved to the `card-feed` branch and a push notification; no card email
is sent any more. STEP 1 of the SOCCER WATCH prompt was rewritten to say so --
"Read the `card-feed` branch, not email" -- but STEP 3 still said "From the most
recent card email, report:", the hard rules still said "Report only what the
emails say", and the closing paragraph still reasoned about "no card email". A
routine following the prompt literally would look for mail that does not exist
and report the card as missing every week.

The prompt still mentions email three times on purpose, and all three warn
*against* it: STEP 1's "not email", STEP 2's caveat about reading the issue #162
notification thread in full (those GitHub notifications are real mail), and the
closing "never from the inbox alone". So this cannot be a ban on the word.

The assertion that carries the weight is the positive one -- STEP 3 must name
the file it reads. The absent-phrase list below is a list of shapes and is
honest about that: it pins the three spellings that were actually wrong, and
cannot catch a fourth. `docs/` prose has needed seven rounds of that in this
repository, which is why the positive check is here as well.
"""

from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "soccer_scheduled_tasks_bridge.md"

#: The card's only delivery path since the email step was removed.
FEED_BRANCH = "card-feed"
CARD_FILE = "latest_card_comment.md"


def _flat(text: str) -> str:
    """Whitespace collapsed, because the prompt is hard-wrapped at ~76 columns.

    Every phrase check here goes through this. The first draft of this file
    asserted `"not email" in prompt` and failed on the real document, where the
    line breaks between "not" and "email" -- and the same break would have let
    `"card email"` walk straight through the ban below. A guard that reads one
    line at a time has already missed 5 of 11 figures in this repository.
    """
    return " ".join(text.split())


def _routine(name: str) -> str:
    """One routine's prompt body, from its fenced block under `Exact routine prompts`."""
    text = DOC.read_text(encoding="utf-8")
    hit = re.search(
        rf"^### {re.escape(name)}.*?\n```text\n(.*?)\n```",
        text, re.MULTILINE | re.DOTALL,
    )
    assert hit, f"no fenced prompt for {name!r}; the heading or the fence moved"
    return hit.group(1)


def test_the_watch_routine_names_the_file_it_reads_the_card_from() -> None:
    """The load-bearing assertion: a source, not the absence of a wrong one."""
    prompt = _routine("SOCCER WATCH (formerly EPL WATCH)")
    step3 = prompt.split("STEP 3", 1)
    assert len(step3) == 2, "the watch routine has no STEP 3 to report the card from"
    body = _flat(step3[1].split("FACTS ABOUT THE MARKETS", 1)[0])
    assert CARD_FILE in body, (
        f"STEP 3 does not say where the card comes from; it must name {CARD_FILE} "
        f"on {FEED_BRANCH}, because no card email is sent"
    )
    assert FEED_BRANCH in body


def test_the_watch_routine_does_not_source_the_card_from_email() -> None:
    """The three spellings that were actually wrong. A shape list, and only that."""
    prompt = _routine("SOCCER WATCH (formerly EPL WATCH)")
    flat = _flat(prompt).lower()
    for phrase in ("card email", "card emails", "the emails say"):
        assert phrase not in flat, (
            f"the prompt sources the card from {phrase!r}; delivery is the "
            f"{FEED_BRANCH} branch and no card email is sent"
        )


def test_the_routine_still_warns_against_reading_the_inbox() -> None:
    """The mentions that must survive.

    Removing them would be the opposite failure: two health checks in a row
    once called the pipeline broken by counting Actions failure mail, and an
    eight-day email outage was inferred from a truncated Gmail thread. Both
    warnings are load-bearing history.
    """
    flat = _flat(_routine("SOCCER WATCH (formerly EPL WATCH)"))
    assert "not email" in flat, "STEP 1 no longer tells the routine to skip email"
    assert "issue #162" in flat
    assert "inbox alone" in flat, (
        "the closing warning against settling a gap from the inbox is gone"
    )


def test_the_quota_is_described_in_the_unit_the_summary_reports() -> None:
    """The prompt asked for a figure the run summary had stopped printing.

    `run_summary._quota_line` reports days at the observed burn, not runs: a
    cost model enumerating named consumers always understates, and the
    provider's counter cannot omit one. A routine asking for "how many runs
    that buys" would either report nothing or convert the figure itself.
    """
    flat = _flat(_routine("SOCCER WATCH (formerly EPL WATCH)"))
    assert "runs that buys" not in flat
    assert "days that buys" in flat and "observed" in flat

    summary = (
        DOC.resolve().parents[1] / "src" / "epl_betting_lab" / "reports" / "run_summary.py"
    ).read_text(encoding="utf-8")
    assert "at the observed burn" in summary, (
        "the run summary no longer phrases the quota that way, so the routine "
        "prompt is now describing something that is not printed"
    )
