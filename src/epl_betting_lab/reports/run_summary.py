"""Render the current state as a GitHub Actions job summary.

A workflow that produces artifacts still asks the reader to download something.
GitHub renders a job summary directly on the run page, so the card can be read
in a browser with no download, no clone, and no terminal — which is the whole
point of automating the refresh.

Markdown rather than HTML because that is what the summary accepts. It is built
from the routine reports, so it contains no credential; a test plants a
key-shaped value in a report and asserts the summary is unaffected.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from collections.abc import Sequence as _Sequence

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.pick_display import (
    NOT_STAKEABLE_LABEL,
    NOT_STAKEABLE_NOTE,
    format_american_odds,
    split_stakeable,
)


SUMMARY_MARKDOWN_FILENAME = "run_summary.md"


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


def _table(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| Match | Market | Selection | Tier | Model | Edge | Price | Book | Units |",
        "|:------|:-------|:----------|:-----|------:|-----:|------:|:-----|------:|",
    ]
    for row in rows:
        prob = row.get("calibrated_model_prob")
        edge = row.get("calibrated_edge")
        units = row.get("suggested_units")
        lines.append(
            f"| {_clean(row.get('home_team'))} v {_clean(row.get('away_team'))} "
            f"| `{_clean(row.get('market'))}` | {_clean(row.get('selection'))} "
            f"| {_clean(row.get('confidence_tier')) or '—'} "
            f"| {f'{float(prob):.1%}' if isinstance(prob, (int, float)) else '—'} "
            f"| {f'{float(edge):+.1%}' if isinstance(edge, (int, float)) else '—'} "
            f"| {format_american_odds(row.get('american_odds'))} "
            f"| {_clean(row.get('book')) or '—'} "
            f"| {_clean(units) if units not in (None, '') else '—'} |"
        )
    lines.append("")
    return lines


#: Measured from consecutive live runs, not derived: the counter moved 14248 ->
#: 14186 -> 14124, and 19612 -> 19540. Sixty-two a run with every market
#: fetched.
#:
#: It read 15 until this was checked, from a measurement taken before the extra
#: markets were added, so the "about N more runs" figure overstated the runway
#: roughly fourfold. A number offered to reassure someone should not be the
#: optimistic one.
REQUESTS_PER_RUN = 62

#: Below this many runs' worth, the summary says so. Quota running dry is one
#: of the ways this automation stops without producing a red X, so the number
#: has to become an argument rather than sit in a table being technically
#: present. Fourteen is about a fortnight at ten runs a week.
LOW_QUOTA_RUNS = 14


def _quota_line(quota: Mapping[str, Any]) -> str:
    """The remaining quota, and how many runs that actually buys."""
    raw = _clean(quota.get("requests_remaining"))
    if not raw:
        return "unknown"
    try:
        remaining = int(float(raw))
    except ValueError:
        return raw
    runs = remaining // REQUESTS_PER_RUN
    if runs <= LOW_QUOTA_RUNS:
        return (
            f"**{remaining}** — about {runs} more run(s). "
            "**Top this up or the schedule stops.**"
        )
    return f"{remaining} (about {runs} more runs)"


def _picks_table(rows: Sequence[Mapping[str, Any]], empty: str) -> list[str]:
    """Render picks, keeping zero-unit rows visibly apart from real plays."""
    if not rows:
        return [f"_{empty}_", ""]
    stakeable, not_stakeable = split_stakeable(rows)
    lines = _table(stakeable) if stakeable else [f"_{empty}_", ""]
    if not_stakeable:
        lines += [f"**{NOT_STAKEABLE_LABEL}**", "", NOT_STAKEABLE_NOTE, ""]
        lines += _table(not_stakeable)
    return lines


def build_run_summary(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
    degraded: _Sequence[str] = (),
) -> str:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    model = _read(outputs / "epl_model_task.json")
    card = _read(outputs / "epl_card_task.json")
    settle = _read(outputs / "epl_settle_preview_task.json")
    generated = _read(outputs / "automated_card.json")
    comparison = _read(outputs / "automated_card_comparison.json")
    shadow = _read(outputs / "provider_shadow_verification.json")

    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    card_ready = bool(card.get("card_ready", False))
    card_generated = bool(generated.get("card_generated", False))
    quota = shadow.get("api_quota") if isinstance(shadow.get("api_quota"), Mapping) else {}

    lines = [
        "# EPL Betting Lab — matchday refresh",
        "",
        f"Generated {stamp.strftime('%Y-%m-%d %H:%M UTC')}. "
        "Recommendations only; no bet is ever placed and settlement is never applied.",
        "",
    ]
    if degraded:
        # Top of the page, before the status table. A reader who stops after the
        # first screen must not come away thinking this was a normal run.
        lines += [
            "> [!WARNING]",
            "> **This run was degraded.** The card below was built from "
            "whatever evidence was available.",
            ">",
        ]
        lines += [f"> - {item}" for item in degraded]
        lines += [""]
    lines += [
        "| | |",
        "|:--|:--|",
        f"| Model | {'Ready' if model.get('epl_card_ready') else 'Blocked'} |",
        f"| Card | {'Ready' if card_ready else 'Blocked'} |",
        f"| Markets included | {', '.join(card.get('included_markets') or []) or 'none'} |",
        f"| Markets excluded | {', '.join(card.get('excluded_markets') or []) or 'none'} |",
        f"| Manual odds entry | {'Required' if card.get('manual_odds_entry_required') else 'Not required'} |",
        f"| Provider run | {_clean(shadow.get('verdict')) or 'unknown'} |",
        f"| Quota remaining | {_quota_line(quota)} |",
        "",
    ]

    if card_ready and card_generated:
        lines += ["## Best bets", ""]
        lines += _picks_table(card.get("best_bets") or [], "No best bets.")
        lines += ["## Leans", ""]
        lines += _picks_table(card.get("leans") or [], "No leans.")
    else:
        lines += [
            "## No card was produced",
            "",
            "This is a **blocked** card, not a card with no value: nothing was "
            "generated, so nothing is being withheld as a judgement.",
            "",
        ]
        # Prefer the generated card's blockers. The routine feeds carry terse
        # status labels ("Needs odds", "Provider not trusted") which name the
        # symptom without naming the fix, and they cascade: four blockers where
        # three are consequences of the first. The generated card already
        # resolved that — it leads with the root cause and carries the command
        # that clears it — so a blocked run summary should say what a person
        # can actually do next.
        root = _clean(generated.get("root_blocker"))
        blockers = (
            generated.get("blockers")
            or card.get("blockers")
            or model.get("blockers")
            or []
        )
        if root:
            lines += [f"**Start here:** {root}", ""]
            remaining = [b for b in blockers if _clean(b) != root]
            if remaining:
                lines.append(
                    f"{len(remaining)} further blocker(s) may clear once that is "
                    "resolved:"
                )
                lines.append("")
                lines += [f"- {blocker}" for blocker in remaining]
                lines.append("")
        else:
            lines += [f"- {blocker}" for blocker in blockers]
            lines.append("")
        next_action = _clean(generated.get("next_action"))
        if next_action and next_action != root:
            lines += [f"Next action: {next_action}", ""]

    if comparison.get("comparable") and not (card_ready and card_generated):
        # A blocked run has no card, so every previous pick counts as "removed".
        # Printed as a bare number that reads as a judgement — 27 picks dropped —
        # when nothing was dropped and nothing was assessed. The comparison is
        # only meaningful between two cards that exist.
        lines += [
            "## Since the previous refresh",
            "",
            "No comparison: this run produced no card, so there is nothing to "
            "compare the previous one against. The previous card's selections "
            "were not withdrawn or reassessed — they were simply not "
            "regenerated.",
            "",
        ]
    elif comparison.get("comparable"):
        lines += [
            "## Since the previous refresh",
            "",
            f"- Added: {len(comparison.get('added') or [])}",
            f"- Removed: {len(comparison.get('removed') or [])}",
            f"- Moved section: {len(comparison.get('moved_section') or [])}",
            f"- Price moved: {len(comparison.get('price_changed') or [])}",
            f"- Unchanged: {comparison.get('unchanged_count', 0)}",
            "",
        ]
        for row in (comparison.get("price_changed") or [])[:10]:
            lines.append(
                f"  - {_clean(row.get('label'))}: "
                f"{format_american_odds(row.get('from_price'))} "
                f"→ {format_american_odds(row.get('to_price'))}"
            )
        if comparison.get("price_changed"):
            lines.append("")
        lines.append(
            "A price that moved is not a pick that was dropped; they are counted "
            "separately."
        )
        lines.append("")

    # How the recommendations have actually done. The only out-of-sample
    # evidence this project has, and it accumulates by itself.
    try:
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
        # A scoreboard that cannot be built must not take the card down with
        # it: it is a report about the past, and the card is about this week.
        lines += [
            "_The recommendation scoreboard could not be built this run._",
            "",
        ]

    lines += [
        "## Settlement",
        "",
        f"- Mode: **{_clean(settle.get('mode')) or 'Preview only'}**",
        f"- Open bets: {settle.get('open_bet_count', 0)}",
        f"- Would settle this run: **{settle.get('would_settle_count', 0)}**",
        "",
        "Settlement is preview-only and has no write path. No bet was placed.",
        "",
    ]
    return "\n".join(lines)


def save_run_summary(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
    degraded: _Sequence[str] = (),
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    text = build_run_summary(output_dir=outputs, now=now, degraded=degraded)
    outputs.mkdir(parents=True, exist_ok=True)
    path = outputs / SUMMARY_MARKDOWN_FILENAME
    path.write_text(text, encoding="utf-8")
    return {"markdown": str(path), "text": text}
