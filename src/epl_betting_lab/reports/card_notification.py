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
from epl_betting_lab.reports.run_summary import _quota_line
from epl_betting_lab.reports.pick_display import (
    format_american_odds,
    format_market_list,
    split_stakeable,
)


ISSUE_TITLE = "EPL Card — this week's picks"

#: Who to mention so the comment actually reaches a person.
#:
#: Posting a comment is not the same as delivering it. On a repository you own,
#: GitHub's default notification setting is "participating and @mentions", so a
#: comment written by Actions on an issue nobody has touched can notify nobody
#: at all — the delivery would look like it worked on every run and quietly
#: reach no one. An explicit mention always notifies, whatever the watch
#: settings are, and needs nothing configured by hand.
NOTIFY_HANDLE = "@cooperross399"


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
    degraded: Sequence[str] = (),
    last_sent: datetime | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Should this run be emailed, and why?

    Returns (should_post, reason). The reason is reported either way, so a run
    that stays quiet can still explain itself in its own job log.

    A degraded run always sends. The reader is being asked to treat silence as
    "nothing moved", and that is only safe if anything going wrong breaks the
    silence — otherwise a week of failures looks exactly like a quiet week.
    """
    if degraded:
        return True, "Something went wrong in this run."
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

    # Nothing changed. Send anyway if nothing has gone out today.
    #
    # Sending only on change was right when a person read the mail: a price
    # drifting is not news. It is wrong for something that reads daily, which
    # then finds a message from days ago and reports it as the state of play —
    # exactly what the first routine run did. A card a day is at most five
    # messages a week and means whatever reads them is never looking at a stale
    # one. A change is still described as a change, because that is the more
    # useful sentence when there is one.
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if last_sent is None or last_sent.astimezone(timezone.utc).date() < moment.date():
        return True, "First card of the day; the selections are unchanged."

    moved_prices = len(comparison.get("price_changed") or [])
    return False, (
        f"Already sent today; same selections ({moved_prices} price move(s))."
    )


def read_degraded(path: Path | str | None) -> list[str]:
    """The reasons this run was degraded, one per line, or none."""
    if not path:
        return []
    target = Path(path)
    if not target.is_file():
        return []
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def build_notification(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
    run_url: str = "",
    degraded: Sequence[str] = (),
    trigger: str = "",
    last_sent: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    card = _read(outputs / "epl_card_task.json")
    generated = _read(outputs / "automated_card.json")
    comparison = _read(outputs / "automated_card_comparison.json")

    should_post, reason = decide(
        card=card,
        generated=generated,
        comparison=comparison,
        degraded=degraded,
        last_sent=last_sent,
        now=now,
    )
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    card_ready = bool(card.get("card_ready", False)) and bool(
        generated.get("card_generated", False)
    )

    # Every run says how it was started, not only the manual ones.
    #
    # Labelling manual runs alone left the other kind unlabelled, which is
    # ambiguous rather than informative: a health check reading an older
    # message could not tell whether "no label" meant scheduled or meant the
    # message predated labelling, and had to say so. Labelling both makes an
    # unlabelled message mean exactly one thing — that it is old.
    manual = trigger == "workflow_dispatch"
    label = {
        "workflow_dispatch": "manual run",
        "schedule": "scheduled run",
    }.get(trigger, "")
    heading = f"## {stamp.strftime('%A %d %B, %H:%M UTC')}"
    if label:
        heading += f" — {label}"
    lines = [
        heading,
        "",
        f"{NOTIFY_HANDLE} — {reason}",
        "",
    ]
    if manual:
        lines += [
            "_This run was started by hand, not by the schedule. If you did not "
            "start it, someone was testing._",
            "",
        ]

    if degraded:
        lines += ["### What went wrong", ""]
        lines += [f"- {item}" for item in degraded]
        lines += [
            "",
            "The card below was still built, from whatever evidence was "
            "available. Treat it with that in mind.",
            "",
        ]

    # Quota belongs in the mail, not only in the run summary. The routine
    # prompts ask for it, and a routine reads email — so asking for something
    # the email does not carry made it report "quota: missing" every week.
    shadow = _read(outputs / "provider_shadow_verification.json")
    quota = shadow.get("api_quota") if isinstance(shadow.get("api_quota"), Mapping) else {}
    quota_line = _quota_line(quota)
    if quota_line != "unknown":
        lines += [f"Provider quota: {quota_line}", ""]

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

    try:
        # OUTPUTS_DIR is imported at module scope. Importing it here as well
        # made it local to this whole function, so the very first line that
        # used it raised UnboundLocalError — before reaching this block.
        from epl_betting_lab.data.loaders import load_matches
        from epl_betting_lab.reports.card_scoreboard import (
            build_scoreboard,
            load_archived_cards,
            render_scoreboard,
        )

        archived = load_archived_cards(outputs / "archive" / "automated_cards")
        if archived:
            lines += render_scoreboard(build_scoreboard(archived, load_matches()))
    except Exception:
        pass

    lines += [
        "---",
        "",
        "Recommendations only. No bet was placed and no settlement was applied.",
        "",
        "You get one card a day while the schedule runs, plus a message "
        "whenever a run goes wrong. So **a day with no message at all means a "
        "run did not happen.**",
        "",
    ]
    if run_url:
        lines += [f"[Full run summary]({run_url})", ""]

    return {"should_post": should_post, "reason": reason, "body": "\n".join(lines)}
