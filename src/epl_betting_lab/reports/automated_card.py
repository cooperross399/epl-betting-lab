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

A third rule joined the first two once a stale card surfaced picks for games
that had already been played:

* **A game that has kicked off is not a play.** Every selection is checked
  against the provider's fixture kickoff times, and one whose game has started
  — or whose kickoff cannot be confirmed — is quarantined into its own section
  rather than presented as a best bet, lean, pass, or stake.
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
from epl_betting_lab.reports.pick_display import (
    NOT_STAKEABLE_LABEL,
    NOT_STAKEABLE_NOTE,
    format_american_odds,
    format_market_list,
    split_stakeable,
)
from epl_betting_lab.reports.current_odds_validation import (
    CurrentOddsValidationError,
)


CARD_JSON_FILENAME = "automated_card.json"
CARD_MARKDOWN_FILENAME = "automated_card.md"

BEST_BETS_SECTION = "Best bets"
LEANS_SECTION = "Leans"
PASSES_SECTION = "Passes / notable avoids"

STAGING_FIXTURES_FILENAME = "upcoming_fixtures_staging.csv"

ALREADY_STARTED_STATUS = "already started"
KICKOFF_UNCONFIRMED_STATUS = "kickoff unconfirmed"

KICKOFF_GUARD_NOTE = (
    "A game that has kicked off is no longer a play. Selections whose kickoff "
    "is at or before generation time, or whose kickoff could not be confirmed "
    "from the provider fixture staging, are listed under 'Already started' and "
    "are never presented as best bets, leans, passes, or stakes."
)

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
    "suggested_units",
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


def _load_kickoffs(path: Path) -> dict[tuple[str, str], pd.Timestamp]:
    """Map (home, away) -> kickoff time from the provider fixture staging.

    A fixture pair listed with conflicting or unparseable kickoff times cannot
    confirm that its game has not started, so the pair is dropped and its
    picks fall to "kickoff unconfirmed" — the safe side of ambiguity.
    """
    if not path.is_file():
        return {}
    try:
        frame = pd.read_csv(path, dtype=str).fillna("")
    except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return {}
    if not {"home_team", "away_team", "commence_time"}.issubset(frame.columns):
        return {}
    kickoffs: dict[tuple[str, str], pd.Timestamp] = {}
    ambiguous: set[tuple[str, str]] = set()
    for _, row in frame.iterrows():
        key = (
            _clean(row.get("home_team")).casefold(),
            _clean(row.get("away_team")).casefold(),
        )
        parsed = pd.to_datetime(
            _clean(row.get("commence_time")), errors="coerce", utc=True
        )
        if pd.isna(parsed):
            ambiguous.add(key)
            continue
        seen = kickoffs.get(key)
        if seen is not None and seen != parsed:
            ambiguous.add(key)
            continue
        kickoffs[key] = parsed
    for key in ambiguous:
        kickoffs.pop(key, None)
    return kickoffs


def _split_started(
    rows: Sequence[Mapping[str, Any]],
    *,
    section: str,
    kickoffs: Mapping[tuple[str, str], pd.Timestamp],
    now: pd.Timestamp,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (playable, quarantined) for one card section."""
    playable: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for row in rows:
        key = (
            _clean(row.get("home_team")).casefold(),
            _clean(row.get("away_team")).casefold(),
        )
        kickoff = kickoffs.get(key)
        if kickoff is None:
            quarantined.append(
                {
                    **row,
                    "original_section": section,
                    "kickoff_status": KICKOFF_UNCONFIRMED_STATUS,
                    "kickoff_time": None,
                }
            )
        elif kickoff <= now:
            quarantined.append(
                {
                    **row,
                    "original_section": section,
                    "kickoff_status": ALREADY_STARTED_STATUS,
                    "kickoff_time": kickoff.isoformat(),
                }
            )
        else:
            playable.append(dict(row))
    return playable, quarantined


def _unit_suggestions(best_bets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Stake units taken from the report's own `suggested_units` column.

    The best-bets pipeline already computes staking. Re-deriving it from the
    confidence tier here would be a second, divergent staking model, so this
    reads the existing value and adds nothing of its own. A pick without a
    usable stake gets no suggestion rather than a guessed one.
    """
    suggestions: list[dict[str, Any]] = []
    for pick in best_bets:
        units = pick.get("suggested_units")
        if units is None or (isinstance(units, float) and pd.isna(units)):
            continue
        try:
            units_value = float(units)
        except (TypeError, ValueError):
            continue
        if units_value <= 0:
            continue
        suggestions.append(
            {
                "home_team": pick.get("home_team"),
                "away_team": pick.get("away_team"),
                "market": pick.get("market"),
                "selection": pick.get("selection"),
                "confidence_tier": pick.get("confidence_tier"),
                "suggested_units": units_value,
                "book": pick.get("book"),
                "basis": (
                    "Existing pipeline `suggested_units`; no second staking "
                    "model was introduced."
                ),
            }
        )
    return suggestions


def _provider_allowlisted_now(policy_path: Path | None, provider_name: str) -> bool:
    """Check the live policy file, not a report that may predate a change.

    The shadow verification report records the policy state at the time it ran.
    Trusting it alone would let a card generate against a provider whose
    allowlist entry has since been removed, so the current file is authoritative.
    """
    path = (
        MANUAL_DIR / "staging_provider_policy.json"
        if policy_path is None
        else Path(policy_path)
    )
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, Mapping):
        return False
    names = payload.get("allowed_provider_names")
    if not isinstance(names, list):
        return False
    return provider_name in {str(item).strip() for item in names}


def build_automated_card(
    *,
    output_dir: Path | None = None,
    card_input_path: Path | None = None,
    policy_path: Path | None = None,
    provider_name: str = "the_odds_api",
    matches_path: Path | None = None,
    fixtures_path: Path | None = None,
    staging_fixtures_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Generate the card from eligible markets, or explain why it cannot."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    card_input = (
        STAGING_DIR / CARD_INPUT_FILENAME
        if card_input_path is None
        else Path(card_input_path)
    )
    staging_fixtures = (
        STAGING_DIR / STAGING_FIXTURES_FILENAME
        if staging_fixtures_path is None
        else Path(staging_fixtures_path)
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

    # Blockers cascade: with no evidence at all, four checks fail and three of
    # them are consequences of the first. Reporting all four sends the reader
    # chasing four problems when there is one, so downstream checks are skipped
    # once a prerequisite has already failed and the reason is stated.
    blockers: list[str] = []
    skipped_checks: list[str] = []

    def _skip(reason: str) -> None:
        skipped_checks.append(reason)

    if not input_report:
        blockers.append(
            "No automated card input report found. Run: "
            "PYTHONPATH=src .venv/bin/python "
            "scripts/run_api_first_card_workflow.py"
        )
        _skip(
            "Market eligibility, provider policy, and staging validation were "
            "not checked: they are read from reports the API-first workflow "
            "produces."
        )
    else:
        if not eligible_markets:
            blockers.append(
                "No market is eligible for automated picks. See "
                "data/outputs/automated_card_input.md for the reason each "
                "market was excluded."
            )
        if not card_input.is_file():
            blockers.append(
                f"Provider-derived card input missing: `{card_input.name}`. "
                "Re-run: PYTHONPATH=src .venv/bin/python "
                "scripts/run_api_first_card_workflow.py"
            )
        if not bool(policy.get("provider_allowed", False)):
            blockers.append(
                "Provider is not allowlisted by the reviewed staging provider "
                "policy. Allowlisting is a reviewed human decision; see "
                "docs/provider_allowlist_approval_github_ui.md"
            )
        elif not _provider_allowlisted_now(policy_path, provider_name):
            # The report says allowed but the live policy disagrees: the policy
            # has changed since that run, and the live file wins.
            blockers.append(
                f"`{provider_name}` is not in `allowed_provider_names` in the "
                "current staging provider policy, even though an earlier report "
                "recorded it as allowed. Re-run provider verification."
            )
        if not bool(staging_validation.get("handoff_eligible", False)):
            blockers.append(
                "Staging validation is not handoff eligible. See "
                "data/outputs/staging_input_validation.md for the failing "
                "checks."
            )

    summary: dict[str, Any] = {
        "report": "Automated EPL Card",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "window_label": str(input_report.get("window_label") or "no dated fixtures"),
        "card_generated": False,
        "odds_source": str(card_input),
        "manual_odds_entry_required": False,
        "included_markets": eligible_markets,
        "excluded_markets": excluded_markets,
        "excluded_market_details": eligibility.get("markets", []),
        "best_bets": [],
        "leans": [],
        "passes_or_avoids": [],
        "already_started": [],
        "unit_suggestions": [],
        "validation_warnings": [],
        "blockers": blockers,
        "root_blocker": blockers[0] if blockers else "",
        "skipped_checks": skipped_checks,
        "exclusion_note": (
            "Excluded markets are unavailable, incomplete, or outside the "
            "reviewed policy allowlist. They are never presented as passes, "
            "avoids, or no-value calls, and no price was invented for them."
        ),
        "kickoff_guard": {
            "checked": False,
            "checked_at": generated_at.isoformat(timespec="seconds"),
            "fixtures_with_confirmed_kickoff": 0,
            "already_started_count": 0,
            "kickoff_unconfirmed_count": 0,
            "note": KICKOFF_GUARD_NOTE,
        },
        "safety": {
            "odds_fabricated": False,
            "protected_files_written": False,
            "bets_placed": False,
            "settlement_applied": False,
            "force_mode_used": False,
        },
    }

    if blockers:
        # Lead with the first blocker: later ones are often downstream of it,
        # and "resolve the listed blockers" is not an instruction.
        summary["next_action"] = (
            f"Start here: {blockers[0]}"
            + (
                f" ({len(blockers) - 1} further blocker(s) may clear once this "
                "is resolved.)"
                if len(blockers) > 1
                else ""
            )
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
    except FileNotFoundError as exc:
        # Missing evidence is a blocked card, not a crash. The rest of this
        # module is careful about that distinction and this path was not: a
        # missing historical dataset raised through the report runner and took
        # the whole refresh down with a traceback, which reads as "the tool is
        # broken" rather than "one input is absent".
        summary["blockers"] = [f"Card generation blocked by missing data: {exc}"]
        summary["next_action"] = (
            f"Start here: {exc} No selection was produced and no price was "
            "invented."
        )
        summary["root_blocker"] = summary["blockers"][0]
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

    # A game that has kicked off — or whose kickoff cannot be confirmed — is
    # not a play. Quarantine such selections out of every section before
    # anything downstream (units, the routine bridge, the emails) sees them.
    kickoffs = _load_kickoffs(staging_fixtures)
    guard_now = pd.Timestamp(generated_at)
    if guard_now.tzinfo is None:
        guard_now = guard_now.tz_localize(timezone.utc)
    already_started: list[dict[str, Any]] = []
    best_bets, quarantined = _split_started(
        _rows(report, BEST_BETS_SECTION),
        section=BEST_BETS_SECTION,
        kickoffs=kickoffs,
        now=guard_now,
    )
    already_started.extend(quarantined)
    leans, quarantined = _split_started(
        _rows(report, LEANS_SECTION),
        section=LEANS_SECTION,
        kickoffs=kickoffs,
        now=guard_now,
    )
    already_started.extend(quarantined)
    passes, quarantined = _split_started(
        _rows(report, PASSES_SECTION),
        section=PASSES_SECTION,
        kickoffs=kickoffs,
        now=guard_now,
    )
    already_started.extend(quarantined)

    summary["kickoff_guard"].update(
        {
            "checked": True,
            "fixtures_with_confirmed_kickoff": len(kickoffs),
            "already_started_count": sum(
                1
                for item in already_started
                if item["kickoff_status"] == ALREADY_STARTED_STATUS
            ),
            "kickoff_unconfirmed_count": sum(
                1
                for item in already_started
                if item["kickoff_status"] == KICKOFF_UNCONFIRMED_STATUS
            ),
        }
    )

    summary.update(
        {
            "card_generated": True,
            "best_bets": best_bets,
            "leans": leans,
            "passes_or_avoids": passes,
            "already_started": already_started,
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
    def _rows_table(rows: Sequence[Mapping[str, Any]]) -> list[str]:
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
                f"| {format_american_odds(row.get('american_odds'), missing='-')} "
                f"| {_clean(row.get('book')) or '-'} |"
            )
        lines.append("")
        return lines

    def _table(rows: Sequence[Mapping[str, Any]], label: str) -> list[str]:
        if not rows:
            return [f"_No {label.lower()}._", ""]
        stakeable, not_stakeable = split_stakeable(rows)
        lines = _rows_table(stakeable) if stakeable else [f"_No {label.lower()}._", ""]
        if not_stakeable:
            lines += [f"**{NOT_STAKEABLE_LABEL}**", "", NOT_STAKEABLE_NOTE, ""]
            lines += _rows_table(not_stakeable)
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
        f"- Included markets: **{format_market_list(summary['included_markets'])}**",
        f"- Excluded markets: **{format_market_list(summary['excluded_markets'])}**",
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
        lines.extend(["## Already started — no longer plays", ""])
        already_started = summary.get("already_started") or []
        guard = summary.get("kickoff_guard") or {}
        lines.extend([str(guard.get("note", KICKOFF_GUARD_NOTE)), ""])
        if already_started:
            lines.extend(
                [
                    "| Match | Market | Selection | Was | Kickoff (UTC) | Why removed |",
                    "|:------|:-------|:----------|:----|:--------------|:------------|",
                    *[
                        f"| {_clean(item.get('home_team'))} v {_clean(item.get('away_team'))} "
                        f"| `{_clean(item.get('market'))}` | {_clean(item.get('selection'))} "
                        f"| {_clean(item.get('original_section'))} "
                        f"| {_clean(item.get('kickoff_time')) or '-'} "
                        f"| {_clean(item.get('kickoff_status'))} |"
                        for item in already_started
                    ],
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    "_None. Every selection's game kicks off after this card "
                    "was generated._",
                    "",
                ]
            )
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
    policy_path: Path | None = None,
    provider_name: str = "the_odds_api",
    matches_path: Path | None = None,
    fixtures_path: Path | None = None,
    staging_fixtures_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    summary = build_automated_card(
        output_dir=outputs,
        card_input_path=card_input_path,
        policy_path=policy_path,
        provider_name=provider_name,
        matches_path=matches_path,
        fixtures_path=fixtures_path,
        staging_fixtures_path=staging_fixtures_path,
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
