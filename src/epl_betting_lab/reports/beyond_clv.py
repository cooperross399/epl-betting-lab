"""Closing-line value for the Beyond the Premier League selections.

The section recorded what it picked and nothing ever read it back. Both
halves of the pair were already on disk — the picks in
`archive/extra_cards/<date>/<time>/extra_competitions_card.json`, restored at
the top of every run, and the near-kickoff prices in `price_feed_extra.csv`,
captured by the Closing Snapshot about twenty minutes before kick-off — and
nothing joined them. `save_live_clv_reports` is wired to the Premier League
archive and the Premier League feed, and `card_scoreboard.load_archived_cards`
globs `*/*/automated_card.json`, so neither has ever seen this section.

That matters more here than anywhere else on the card. The international pool
cannot be backtested at all: no free archive carries international prices, and
the section's own note says forward CLV is its only possible evidence. Without
this the Nations League selections accrue no evidence in either direction,
however long they run.

The arithmetic is not reimplemented. `build_live_clv` already does it and has
been measured; this converts the record into the shape it expects and hands it
the right feed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.live_clv import (
    build_live_clv,
    render_live_clv,
    summarize_live_clv,
)

#: Where `save_extra_card_record` archives a timestamped copy of every record.
BEYOND_ARCHIVE_GLOB = "*/*/extra_competitions_card.json"

REPORT_FILENAME = "beyond_clv_report.md"
DETAIL_FILENAME = "beyond_clv_bets.csv"
SUMMARY_FILENAME = "beyond_clv_by_market.csv"


def load_beyond_records(archive_root: Path) -> list[dict[str, Any]]:
    """Every archived Beyond record, oldest first."""
    if not archive_root.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(archive_root.glob(BEYOND_ARCHIVE_GLOB)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping):
            records.append(dict(payload))
    return records


def as_cards(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The records in the shape `first_recommendations` reads.

    It wants `card_generated`, `generated_at` and `best_bets`. A record has
    `generated_at` and `selections`, and is written for every run including
    the ones that selected nothing — so `card_generated` is asserted here
    rather than stored, because a record existing IS the run having produced
    one. Leans are absent by construction: `_stake` drops anything unstaked,
    and this section stakes every row it prints.
    """
    return [
        {
            "card_generated": True,
            "generated_at": record.get("generated_at", ""),
            "best_bets": list(record.get("selections") or []),
            "leans": [],
        }
        for record in records
    ]


def build_beyond_clv(
    records: Sequence[Mapping[str, Any]],
    feed: pd.DataFrame,
    *,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """One row per Beyond recommendation, with whatever the feed can say.

    The join runs on `provider_event_id`, which `_feed_keys` prefers over
    names. It has to: the record stores club names mapped onto Football-Data's
    spelling and the feed stores the provider's, so a name join would compare
    "Roma" against "AS Roma" and find nothing. The same mismatch already made
    the freshness audit report three selections it could not check.
    """
    return build_live_clv(as_cards(records), feed, now=now)


def save_beyond_clv_reports(
    records: Sequence[Mapping[str, Any]],
    feed: pd.DataFrame,
    output_dir: Path | None = None,
    *,
    now: pd.Timestamp | None = None,
) -> dict[str, Path]:
    """Write the Beyond CLV detail, summary and report."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    outputs.mkdir(parents=True, exist_ok=True)
    frame = build_beyond_clv(records, feed, now=now)
    summary = summarize_live_clv(frame)
    paths = {
        "detail": outputs / DETAIL_FILENAME,
        "summary": outputs / SUMMARY_FILENAME,
        "markdown": outputs / REPORT_FILENAME,
    }
    frame.to_csv(paths["detail"], index=False)
    summary.to_csv(paths["summary"], index=False)

    body = render_live_clv(
        frame, summary, feed_rows=0 if feed is None else len(feed)
    )
    paths["markdown"].write_text(
        "# Beyond the Premier League — closing-line value\n\n"
        "The Premier League CLV report covers `automated_card.json` only. "
        "These are the other competitions' selections, scored the same way "
        "against `price_feed_extra.csv`.\n\n"
        "For the international pool this is not one source of evidence among "
        "several. No free archive carries international prices, so the "
        "section cannot be backtested at all and this is the only thing that "
        "will ever say whether it is any good.\n\n" + body,
        encoding="utf-8",
    )
    return paths
