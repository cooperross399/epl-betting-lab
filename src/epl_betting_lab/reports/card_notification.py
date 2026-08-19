"""Decide whether this run's card is worth an email, and write it.

The schedule runs five times a week. Emailing every run would train the reader
to ignore the mail, which is the failure mode that matters most here: an alert
nobody opens is worse than no alert, because it looks like coverage.

So a run posts only when the *selections* changed — one added, dropped, or
moved between best bets and leans. A price drifting a few cents is not news; it
is already visible in the run summary for anyone who wants it.

That makes silence meaningful, and silence is only safe to read if a broken run
is loud. It is: GitHub emails the workflow's author when a scheduled run fails.
So no email means the run happened and the card did not change — not that
nothing ran.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.pick_display import (
    format_american_odds,
    format_market_list,
    split_stakeable,
)


ISSUE_TITLE = "EPL Card — this week's picks"


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _rows(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| Match | Market | Selection | Tier | Edge | Price | Book | Units |",
        "|:------|:-------|:----------|:-----|-----:|------:|:-----|------:|",
    ]
    for row in rows:
        edge = row.get("calibrated_edge")
        lines.append(
            f"| {_clean(row.get('home_team'))} v {_clean(row.get('away_team'))} "
            f"| `{_clean(row.get('market'))}` | {_clean(row.get('selection'))} "
            f"| {_clean(row.get('confidence_tier')) or '—'} "
            f"| {f'{float(edge):+.1%}' if isinstance(edge, (int, float)) else '—'} "
            f"| {format_american_odds(row.get('american_odds'))} "
            f"| {_clean(row.get('book')) or '—'} "
            f"| {_clean(row.get('suggested_units'))} |"
        )
    lines.append("")
    return lines


def decide(
    *,
    card: Mapping[str, Any],
    generated: Mapping[str, Any],
    comparison: Mapping[str, Any],
) -> tuple[bool, str]:
    """Should this run be emailed, and why?

    Returns (should_post, reason). The reason is reported either way, so a run
    that stays quiet can still explain itself in its own job log.
    """
    card_ready = bool(card.get("card_ready", False)) and bool(
        generated.get("card_generated", False)
    )
    added = list(comparison.get("added") or [])
    removed = list(comparison.get("removed") or [])
    moved = list(comparison.get("moved_section") or [])

    if not card_ready:
        # A card that existed and now does not is worth knowing about. A run
        # that was already blocked and stayed blocked is not news, and would
        # otherwise email on every run of a broken week.
        if removed:
            return True, "The card is blocked; the previous card's picks are gone."
        return False, "No card, and none previously — nothing new to report."

    if not comparison.get("comparable"):
        return True, "First card with nothing to compare against."

    changes = len(added) + len(removed) + len(moved)
    if changes:
        parts = []
        if added:
            parts.append(f"{len(added)} added")
        if removed:
            parts.append(f"{len(removed)} dropped")
        if moved:
            parts.append(f"{len(moved)} moved section")
        return True, "Selections changed: " + ", ".join(parts) + "."

    moved_prices = len(comparison.get("price_changed") or [])
    return False, (
        f"Same selections as the previous run ({moved_prices} price move(s) only)."
    )


def build_notification(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
    run_url: str = "",
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    card = _read(outputs / "epl_card_task.json")
    generated = _read(outputs / "automated_card.json")
    comparison = _read(outputs / "automated_card_comparison.json")

    should_post, reason = decide(
        card=card, generated=generated, comparison=comparison
    )
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    card_ready = bool(card.get("card_ready", False)) and bool(
        generated.get("card_generated", False)
    )

    lines = [
        f"## {stamp.strftime('%A %d %B, %H:%M UTC')}",
        "",
        f"_{reason}_",
        "",
    ]

    if card_ready:
        best, _ = split_stakeable(card.get("best_bets") or [])
        leans, _ = split_stakeable(card.get("leans") or [])
        lines += [
            f"Markets: **{format_market_list(card.get('included_markets'))}** "
            f"(excluded: {format_market_list(card.get('excluded_markets'))})",
            "",
            "### Best bets",
            "",
        ]
        lines += _rows(best) if best else ["_None._", ""]
        lines += ["### Leans", ""]
        lines += _rows(leans) if leans else ["_None._", ""]

        added = comparison.get("added") or []
        removed = comparison.get("removed") or []
        moved = comparison.get("moved_section") or []
        if added or removed or moved:
            lines += ["### What changed", ""]
            for row in added:
                lines.append(f"- **Added:** {_clean(row.get('label'))}")
            for row in removed:
                lines.append(f"- **Dropped:** {_clean(row.get('label'))}")
            for row in moved:
                lines.append(f"- **Moved section:** {_clean(row.get('label'))}")
            lines.append("")
    else:
        lines += [
            "### No card was produced",
            "",
            "This is a **blocked** card, not a card with no value: nothing was "
            "generated, so nothing is being withheld as a judgement.",
            "",
        ]
        root = _clean(generated.get("root_blocker"))
        if root:
            lines += [f"**Start here:** {root}", ""]

    lines += [
        "---",
        "",
        "Recommendations only. No bet was placed and no settlement was applied.",
        "",
        "You are emailed only when the selections change — a price drifting is "
        "not news. A failed run emails you separately, so **no message means "
        "the run happened and the picks did not move.**",
        "",
    ]
    if run_url:
        lines += [f"[Full run summary]({run_url})", ""]

    return {"should_post": should_post, "reason": reason, "body": "\n".join(lines)}
