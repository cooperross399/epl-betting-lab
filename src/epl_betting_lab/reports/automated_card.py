"""Generate the automated EPL card from provider-derived odds.

This is the last step of the API-first workflow: the existing Thursday best-bets
pipeline is pointed at the provider-derived card input instead of a hand-filled
`current_odds.csv`. No model math is changed — the same model, calibration, and
ranking run against a different odds source.

Two rules shape everything here:

* **Only eligible markets produce picks.** Rows for excluded markets are dropped
  before the report is assembled, and again after, so an excluded market cannot
  appear as a best bet, a lean, or a pass. It is reported under
  `excluded_markets` with its reason.
* **An excluded market is never a "no value" call.** Passes and avoids are
  genuine model judgements about markets that were actually priced and modelled.
  A market the provider could not supply is a different thing entirely, and
  conflating them would misrepresent the card.

The card refuses to generate at all unless the provider is trusted and the
eligibility gate passes, so a blocked state yields no selections rather than
placeholder ones.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR, STAGING_DIR
from epl_betting_lab.dashboard_actions import run_thursday_best_bets_report
from epl_betting_lab.reports.automated_card_input import CARD_INPUT_FILENAME
from epl_betting_lab.reports.current_odds_validation import (
    CurrentOddsValidationError,
)
from epl_betting_lab.selected_slate import SELECTED_WEEK1_LABEL


CARD_JSON_FILENAME = "automated_card.json"
CARD_MARKDOWN_FILENAME = "automated_card.md"

BEST_BETS_SECTION = "Best bets"
LEANS_SECTION = "Leans"
PASSES_SECTION = "Passes / notable avoids"

#: Columns carried into the routine-facing payload.
PICK_FIELDS = (
    "home_team",
    "away_team",
    "market",
    "selection",
    "status",
    "confidence_tier",
    "calibrated_model_prob",
    "calibrated_edge",
    "raw_model_prob",
    "raw_edge",
    "fair_american",
    "american_odds",
    "book",
    "notes",
)


def _clean(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _section(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(frame: pd.DataFrame, section: str) -> list[dict[str, Any]]:
    if frame.empty or "section" not in frame.columns:
        return []
    subset = frame[frame["section"].astype(str) == section]
    records: list[dict[str, Any]] = []
    for _, row in subset.iterrows():
        record: dict[str, Any] = {}
        for field in PICK_FIELDS:
            value = row.get(field)
            if isinstance(value, float) and pd.isna(value):
                value = None
            record[field] = value
        records.append(record)
    return records


def _unit_suggestions(best_bets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Stake units carried from the existing confidence tiers.

    This reads the tier the model already assigned; it does not introduce a new
    staking model. Tiers the report does not recognise get no suggestion rather
    than a guessed one.
    """
    tier_units = {"A": 1.0, "B": 0.75, "C": 0.5}
    suggestions: list[dict[str, Any]] = []
    for pick in best_bets:
        tier = _clean(pick.get("confidence_tier")).upper()[:1]
        units = tier_units.get(tier)
        if units is None:
            continue
        suggestions.append(
            {
                "home_team": pick.get("home_team"),
                "away_team": pick.get("away_team"),
                "market": pick.get("market"),
                "selection": pick.get("selection"),
                "confidence_tier": pick.get("confidence_tier"),
                "suggested_units": units,
                "basis": "Existing confidence tier; no new staking model.",
            }
        )
    return suggestions


def build_automated_card(
    *,
    output_dir: Path | None = None,
    card_input_path: Path | None = None,
    matches_path: Path | None = None,
    fixtures_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Generate the card from eligible markets, or explain why it cannot."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    card_input = (
        STAGING_DIR / CARD_INPUT_FILENAME
        if card_input_path is None
        else Path(card_input_path)
    )
    generated_at = now or datetime.now(timezone.utc)

    input_report = _read_json(outputs / "automated_card_input.json")
    shadow = _read_json(outputs / "provider_shadow_verification.json")
    eligibility = _section(input_report, "eligibility")

    eligible_markets = [
        str(item).strip().lower()
        for item in (eligibility.get("eligible_markets") or [])
    ]
    excluded_markets = list(eligibility.get("excluded_markets") or [])
    staging_validation = _section(shadow, "staging_validation")
    policy = _section(shadow, "provider_policy")

    blockers: list[str] = []
    if not input_report:
        blockers.append(
            "No automated card input report found. Run the API-first workflow."
        )
    if not eligible_markets:
        blockers.append("No market is eligible for automated picks.")
    if not card_input.is_file():
        blockers.append(f"Provider-derived card input missing: `{card_input.name}`.")
    if not bool(policy.get("provider_allowed", False)):
        blockers.append(
            "Provider is not allowlisted by the reviewed staging provider policy."
        )
    if not bool(staging_validation.get("handoff_eligible", False)):
        blockers.append("Staging validation is not handoff eligible.")

    summary: dict[str, Any] = {
        "report": "Automated EPL Card",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "window_label": SELECTED_WEEK1_LABEL,
        "card_generated": False,
        "odds_source": str(card_input),
        "manual_odds_entry_required": False,
        "included_markets": eligible_markets,
        "excluded_markets": excluded_markets,
        "excluded_market_details": eligibility.get("markets", []),
        "best_bets": [],
        "leans": [],
        "passes_or_avoids": [],
        "unit_suggestions": [],
        "validation_warnings": [],
        "blockers": blockers,
        "exclusion_note": (
            "Excluded markets are unavailable, incomplete, or outside the "
            "reviewed policy allowlist. They are never presented as passes, "
            "avoids, or no-value calls, and no price was invented for them."
        ),
        "safety": {
            "odds_fabricated": False,
            "protected_files_written": False,
            "bets_placed": False,
            "settlement_applied": False,
            "force_mode_used": False,
        },
    }

    if blockers:
        summary["next_action"] = (
            "Resolve the listed blockers before an automated card can be "
            "generated. No selection was produced."
        )
        return summary

    try:
        paths = run_thursday_best_bets_report(
            current_odds_path=card_input,
            output_dir=outputs,
            force=False,
            archive=False,
            matches_path=matches_path,
            fixtures_path=fixtures_path,
        )
    except CurrentOddsValidationError as exc:
        summary["blockers"] = [f"Card generation blocked by validation: {exc}"]
        summary["next_action"] = (
            "Review the current odds validation report. No selection was "
            "produced and no price was invented."
        )
        return summary

    try:
        report = pd.read_csv(paths["csv"])
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
        summary["blockers"] = ["The generated card report could not be read."]
        summary["next_action"] = "Re-run the automated card workflow."
        return summary

    # Defence in depth: the input already contains only eligible markets, but
    # filter again so a future change upstream cannot leak an excluded market
    # into published picks.
    if not report.empty and "market" in report.columns:
        market_key = report["market"].astype(str).str.strip().str.lower()
        leaked = sorted(set(market_key) - set(eligible_markets))
        report = report[market_key.isin(eligible_markets)]
    else:
        leaked = []

    best_bets = _rows(report, BEST_BETS_SECTION)
    summary.update(
        {
            "card_generated": True,
            "best_bets": best_bets,
            "leans": _rows(report, LEANS_SECTION),
            "passes_or_avoids": _rows(report, PASSES_SECTION),
            "unit_suggestions": _unit_suggestions(best_bets),
            "markets_filtered_out": leaked,
            "card_report_csv": str(paths["csv"]),
            "card_report_markdown": str(paths["markdown"]),
            "next_action": (
                "Review the generated card before acting on it. Provider odds "
                "are trusted for eligible markets only; excluded markets are "
                "listed separately and are not no-value calls."
            ),
        }
    )
    return summary


def render_automated_card(summary: Mapping[str, Any]) -> str:
    def _table(rows: Sequence[Mapping[str, Any]], label: str) -> list[str]:
        if not rows:
            return [f"_No {label.lower()}._", ""]
        lines = [
            "| Match | Market | Selection | Tier | Model prob | Edge | Price | Book |",
            "|:------|:-------|:----------|:-----|:-----------|:-----|:------|:-----|",
        ]
        for row in rows:
            prob = row.get("calibrated_model_prob")
            edge = row.get("calibrated_edge")
            lines.append(
                f"| {_clean(row.get('home_team'))} v {_clean(row.get('away_team'))} "
                f"| `{_clean(row.get('market'))}` | {_clean(row.get('selection'))} "
                f"| {_clean(row.get('confidence_tier')) or '-'} "
                f"| {f'{float(prob):.1%}' if isinstance(prob, (int, float)) else '-'} "
                f"| {f'{float(edge):+.1%}' if isinstance(edge, (int, float)) else '-'} "
                f"| {_clean(row.get('american_odds')) or '-'} "
                f"| {_clean(row.get('book')) or '-'} |"
            )
        lines.append("")
        return lines

    lines = [
        "# Automated EPL Card",
        "",
        (
            "Generated from provider-derived odds for eligible markets only. No "
            "price was invented and no manual odds entry was required."
        ),
        "",
        f"- Card generated: **{'Yes' if summary['card_generated'] else 'No'}**",
        f"- Selected window: **{summary['window_label']}**",
        f"- Included markets: **{summary['included_markets'] or 'none'}**",
        f"- Excluded markets: **{summary['excluded_markets'] or 'none'}**",
        f"- Odds source: `{summary['odds_source']}`",
        (
            "- Manual odds entry required: "
            f"**{'Yes' if summary['manual_odds_entry_required'] else 'No'}**"
        ),
        "",
    ]

    if not summary["card_generated"]:
        lines.extend(
            [
                "## Blocked",
                "",
                *[f"- {item}" for item in summary["blockers"]],
                "",
                "No best bet, lean, pass, or stake was produced.",
                "",
            ]
        )
    else:
        lines.extend(["## Best bets", ""])
        lines.extend(_table(summary["best_bets"], "best bets"))
        lines.extend(["## Leans", ""])
        lines.extend(_table(summary["leans"], "leans"))
        lines.extend(["## Passes / notable avoids", ""])
        lines.extend(_table(summary["passes_or_avoids"], "passes"))
        lines.extend(["## Unit suggestions", ""])
        if summary["unit_suggestions"]:
            lines.extend(
                [
                    "| Match | Market | Selection | Tier | Units |",
                    "|:------|:-------|:----------|:-----|:------|",
                    *[
                        f"| {_clean(item.get('home_team'))} v {_clean(item.get('away_team'))} "
                        f"| `{_clean(item.get('market'))}` | {_clean(item.get('selection'))} "
                        f"| {_clean(item.get('confidence_tier'))} "
                        f"| {item.get('suggested_units')} |"
                        for item in summary["unit_suggestions"]
                    ],
                    "",
                ]
            )
        else:
            lines.extend(["_No unit suggestions._", ""])

    lines.extend(
        [
            "## Excluded markets",
            "",
            summary["exclusion_note"],
            "",
        ]
    )
    for market in summary.get("excluded_market_details", []) or []:
        if isinstance(market, Mapping) and not market.get("usable_for_picks", True):
            lines.append(f"- `{market.get('market')}`: {market.get('reason')}")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Odds fabricated: **No**",
            "- Protected files written: **No**",
            "- Bets placed: **No**",
            "- Settlement applied: **No**",
            "- Force mode used: **No**",
            "",
            "## Next action",
            "",
            str(summary.get("next_action", "")),
            "",
        ]
    )
    return "\n".join(lines)


def save_automated_card(
    *,
    output_dir: Path | None = None,
    card_input_path: Path | None = None,
    matches_path: Path | None = None,
    fixtures_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    summary = build_automated_card(
        output_dir=outputs,
        card_input_path=card_input_path,
        matches_path=matches_path,
        fixtures_path=fixtures_path,
        now=now,
    )
    outputs.mkdir(parents=True, exist_ok=True)
    json_path = outputs / CARD_JSON_FILENAME
    markdown_path = outputs / CARD_MARKDOWN_FILENAME
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_automated_card(summary), encoding="utf-8")
    return {"summary": summary, "json": str(json_path), "markdown": str(markdown_path)}
