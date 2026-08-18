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

from epl_betting_lab.config import OUTPUTS_DIR


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


def _picks_table(rows: Sequence[Mapping[str, Any]], empty: str) -> list[str]:
    if not rows:
        return [f"_{empty}_", ""]
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
            f"| {_clean(row.get('american_odds')) or '—'} "
            f"| {_clean(row.get('book')) or '—'} "
            f"| {_clean(units) if units not in (None, '') else '—'} |"
        )
    lines.append("")
    return lines


def build_run_summary(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
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
        "| | |",
        "|:--|:--|",
        f"| Model | {'Ready' if model.get('epl_card_ready') else 'Blocked'} |",
        f"| Card | {'Ready' if card_ready else 'Blocked'} |",
        f"| Markets included | {', '.join(card.get('included_markets') or []) or 'none'} |",
        f"| Markets excluded | {', '.join(card.get('excluded_markets') or []) or 'none'} |",
        f"| Manual odds entry | {'Required' if card.get('manual_odds_entry_required') else 'Not required'} |",
        f"| Provider run | {_clean(shadow.get('verdict')) or 'unknown'} |",
        f"| Quota remaining | {_clean(quota.get('requests_remaining')) or 'unknown'} |",
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
        for blocker in card.get("blockers") or model.get("blockers") or []:
            lines.append(f"- {blocker}")
        lines.append("")

    if comparison.get("comparable"):
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
                f"  - {_clean(row.get('label'))}: {_clean(row.get('from_price'))} "
                f"→ {_clean(row.get('to_price'))}"
            )
        if comparison.get("price_changed"):
            lines.append("")
        lines.append(
            "A price that moved is not a pick that was dropped; they are counted "
            "separately."
        )
        lines.append("")

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
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    text = build_run_summary(output_dir=outputs, now=now)
    outputs.mkdir(parents=True, exist_ok=True)
    path = outputs / SUMMARY_MARKDOWN_FILENAME
    path.write_text(text, encoding="utf-8")
    return {"markdown": str(path), "text": text}
