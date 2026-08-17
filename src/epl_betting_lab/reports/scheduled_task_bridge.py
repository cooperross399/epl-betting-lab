"""Bridge reports for the Claude scheduled tasks/routines.

Three routines consume this repository:

* **EPL Model** — is the model ready, and is the card allowed to run?
* **EPL CARD** — the card itself, which must refuse to invent picks.
* **EPL SETTLE (IGNORE)** — preview only; never settles anything.

Each builder reads existing report JSON produced by the other commands and
returns a single status object the routine can act on. Nothing here re-runs a
provider, fetches odds, edits a protected manual file, or writes a bet. The
settle bridge opens `bet_ledger.csv` read-only and never writes it back.

Design rule: when evidence is missing, the answer is "not ready" with a named
blocker. Absence of a blocker is never inferred from absence of a report.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR, PROJECT_ROOT
from epl_betting_lab.selected_slate import SELECTED_WEEK1_LABEL


MODEL_TASK_JSON = "epl_model_task.json"
MODEL_TASK_MARKDOWN = "epl_model_task.md"
CARD_TASK_JSON = "epl_card_task.json"
CARD_TASK_MARKDOWN = "epl_card_task.md"
SETTLE_TASK_JSON = "epl_settle_preview_task.json"
SETTLE_TASK_MARKDOWN = "epl_settle_preview_task.md"

#: What to do about each named blocker. The vocabulary is deliberately terse so
#: it reads well in a status line, which leaves the label alone saying nothing
#: about the remedy. These fill that gap.
BLOCKER_REMEDIES: dict[str, str] = {
    "Needs odds": (
        "Rebuild the provider-derived card input: "
        "scripts/run_api_first_card_workflow.py"
    ),
    "Needs mapping": (
        "A provider team name has no reviewed project mapping. Add it to "
        "src/epl_betting_lab/providers/team_names.py, deliberately."
    ),
    "Needs BTTS": (
        "BTTS is unavailable from the last provider run. Re-run the provider "
        "with --include-event-markets, or leave BTTS excluded."
    ),
    "Needs validation": (
        "See data/outputs/staging_input_validation.md for the failing checks."
    ),
    "Provider not trusted": (
        "The provider is not allowlisted. That is a reviewed human decision: "
        "docs/provider_allowlist_approval_github_ui.md"
    ),
    "Needs fixtures": (
        "Upcoming fixtures are stale or unreadable. Refresh "
        "data/manual/upcoming_fixtures.csv."
    ),
}


#: Canonical blocker vocabulary shared by the routines.
BLOCKER_NEEDS_ODDS = "Needs odds"
BLOCKER_NEEDS_MAPPING = "Needs mapping"
BLOCKER_NEEDS_BTTS = "Needs BTTS"
BLOCKER_NEEDS_VALIDATION = "Needs validation"
BLOCKER_PROVIDER_NOT_TRUSTED = "Provider not trusted"
BLOCKER_NEEDS_FIXTURES = "Needs fixtures"

CARD_STATUSES = ("Ready", "Blocked", "Not checked")


def _now(now: datetime | None) -> str:
    moment = now or datetime.now(timezone.utc)
    return moment.isoformat(timespec="seconds")


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    """Return (payload, error). A missing report is an empty payload, not a raise."""
    if not path.is_file():
        return {}, f"Report not found: `{path.name}`."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"Report could not be read (`{path.name}`): {type(exc).__name__}."
    if not isinstance(payload, Mapping):
        return {}, f"Report `{path.name}` is not a JSON object."
    return dict(payload), ""


def _section(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _relative(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def _write_pair(
    payload: Mapping[str, Any],
    markdown: str,
    output_dir: Path,
    *,
    json_name: str,
    markdown_name: str,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / json_name
    markdown_path = output_dir / markdown_name
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _gather_evidence(output_dir: Path) -> dict[str, Any]:
    """Read the upstream reports the routines depend on."""
    readiness, readiness_error = _read_json(output_dir / "week1_launch_readiness.json")
    shadow, shadow_error = _read_json(output_dir / "provider_shadow_verification.json")
    validation, validation_error = _read_json(
        output_dir / "staging_input_validation.json"
    )
    card_input, card_input_error = _read_json(
        output_dir / "automated_card_input.json"
    )
    discovery, discovery_error = _read_json(
        output_dir / "provider_market_discovery.json"
    )
    card, card_error = _read_json(output_dir / "automated_card.json")
    return {
        "automated_card": card,
        "automated_card_error": card_error,
        "market_discovery": discovery,
        "market_discovery_error": discovery_error,
        "week1_readiness": readiness,
        "week1_readiness_error": readiness_error,
        "provider_shadow": shadow,
        "provider_shadow_error": shadow_error,
        "staging_validation": validation,
        "staging_validation_error": validation_error,
        "automated_card_input": card_input,
        "automated_card_input_error": card_input_error,
    }


def _market_investigation(discovery: Mapping[str, Any]) -> dict[str, Any]:
    """Why each excluded market is excluded, in reviewable terms.

    A market must never read as "excluded because it lost" — exclusion here is
    always about data availability. Profitability is only ever assessed for
    eligible markets with trusted odds.
    """
    totals = _section(discovery, "totals_classification")
    btts = _section(discovery, "btts_classification")
    return {
        "available": bool(discovery),
        "totals": {
            "status": _clean(totals.get("status")) or "not_checked",
            "events_with_required_line": int(
                totals.get("events_with_required_line", 0) or 0
            ),
            "events_total": int(totals.get("events_total", 0) or 0),
            "root_cause": _clean(totals.get("root_cause")),
            "endpoint_limited": bool(totals.get("endpoint_limited", False)),
            "parser_defect": bool(totals.get("parser_defect", False)),
            "recommended_action": _clean(totals.get("recommended_action")),
        },
        "btts": {
            "status": _clean(btts.get("status")) or "not_checked",
            "events_with_btts": int(btts.get("events_with_btts", 0) or 0),
            "events_total": int(btts.get("events_total", 0) or 0),
            "checked_event_endpoint": bool(btts.get("checked_event_endpoint", False)),
            "endpoint_limited": bool(btts.get("endpoint_limited", False)),
            "root_cause": _clean(btts.get("root_cause")),
            "recommended_action": _clean(btts.get("recommended_action")),
        },
        "profitability_note": (
            "Markets are excluded for data availability only. Profitability is "
            "evaluated solely for eligible markets backed by trusted odds, never "
            "as a reason to exclude a market here."
        ),
    }


def _market_eligibility(card_input: Mapping[str, Any]) -> dict[str, Any]:
    """Summarise per-market eligibility from the automated card input report."""
    eligibility = _section(card_input, "eligibility")
    markets = eligibility.get("markets", [])
    markets = markets if isinstance(markets, list) else []
    return {
        "available": bool(card_input),
        "included_markets": list(eligibility.get("eligible_markets", []) or []),
        "excluded_markets": list(eligibility.get("excluded_markets", []) or []),
        "unavailable_markets": list(eligibility.get("unavailable_markets", []) or []),
        "incomplete_markets": list(eligibility.get("incomplete_markets", []) or []),
        "disabled_markets": list(eligibility.get("disabled_markets", []) or []),
        "any_market_eligible": bool(eligibility.get("any_market_eligible", False)),
        "markets": markets,
        "card_input_written": bool(card_input.get("card_input_written", False)),
        "card_input_path": _clean(card_input.get("card_input_path")),
        "card_input_row_count": int(card_input.get("row_count", 0) or 0),
        "manual_entry_required": bool(card_input.get("manual_entry_required", False)),
        "note": (
            "Excluded markets are unavailable, incomplete, or disabled. They are "
            "never reported as passes or no-value calls."
        ),
    }


def _provider_status(shadow: Mapping[str, Any]) -> dict[str, Any]:
    staging = _section(shadow, "staging_validation")
    policy = _section(shadow, "provider_policy")
    mapping = _section(shadow, "team_mapping")
    btts = _section(shadow, "btts_availability")
    core = _section(shadow, "core_market_coverage")
    slate = _section(shadow, "slate_coverage")
    return {
        "verdict": _clean(shadow.get("verdict")) or "Not checked",
        "mode": _clean(shadow.get("mode")) or "Not checked",
        "generated_at": _clean(shadow.get("generated_at")),
        "handoff_eligible": bool(staging.get("handoff_eligible", False)),
        "staging_validation_verdict": _clean(staging.get("verdict")) or "Not checked",
        "provider_allowed": bool(policy.get("provider_allowed", False)),
        "team_mapping_status": _clean(mapping.get("status")) or "Not checked",
        "team_mapping_coverage": mapping.get("coverage_percentage"),
        "unmapped_teams": list(mapping.get("unmapped_teams", []) or []),
        "btts_status": _clean(btts.get("status")) or "Not checked",
        "btts_row_count": int(btts.get("btts_row_count", 0) or 0),
        "core_market_status": _clean(core.get("status")) or "Not checked",
        "slate_coverage": slate,
        "trusted": False,
    }


def _odds_status(readiness: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "readiness_status": _clean(readiness.get("status")) or "Not checked",
        "odds_file_status": _clean(readiness.get("odds_file_status")) or "Not checked",
        "completeness_percentage": float(
            readiness.get("odds_completeness_percentage", 0.0) or 0.0
        ),
        "missing_odds_count": int(readiness.get("missing_odds_count", 0) or 0),
        "invalid_odds_issue_count": int(
            readiness.get("invalid_odds_issue_count", 0) or 0
        ),
        "validation_warning_count": int(
            readiness.get("validation_warning_count", 0) or 0
        ),
        "selected_window": _clean(readiness.get("selected_window"))
        or SELECTED_WEEK1_LABEL,
        "selected_window_fixture_count": int(
            readiness.get("selected_window_fixture_count", 0) or 0
        ),
        "fixtures_outside_selected_window_count": int(
            readiness.get("fixtures_outside_selected_window_count", 0) or 0
        ),
        "odds_rows_outside_selected_window_count": int(
            readiness.get("odds_rows_outside_selected_window_count", 0) or 0
        ),
        "slate_warnings": list(readiness.get("slate_warnings", []) or []),
        "fixture_status": _clean(readiness.get("fixture_status")) or "Not checked",
        "upcoming_fixture_count": int(readiness.get("upcoming_fixture_count", 0) or 0),
    }


def _collect_blockers(
    odds: Mapping[str, Any],
    provider: Mapping[str, Any],
    evidence: Mapping[str, Any],
    eligibility: Mapping[str, Any] | None = None,
) -> list[str]:
    """Named blockers, in the vocabulary the routines report back.

    In API-first mode the odds source is the provider, not the manual template.
    An empty `current_odds.csv` is therefore not a blocker, and a market the
    provider does not offer (BTTS) is excluded rather than demanded.
    """
    blockers: list[str] = []
    eligibility = eligibility or {}
    api_first = bool(eligibility.get("available")) and bool(
        eligibility.get("any_market_eligible")
    )

    # The readiness report renders fixture status as e.g. "Fresh (20 upcoming
    # match(es))", so match on the leading state rather than the whole string.
    fixture_status = _clean(odds.get("fixture_status"))
    if not (
        fixture_status.startswith("Fresh") or fixture_status == "Not checked"
    ):
        blockers.append(BLOCKER_NEEDS_FIXTURES)

    if api_first:
        # Odds come from provider staging. Manual completeness is irrelevant.
        if not eligibility.get("card_input_written"):
            blockers.append(BLOCKER_NEEDS_ODDS)
    else:
        if evidence.get("week1_readiness_error"):
            blockers.append(BLOCKER_NEEDS_VALIDATION)
        if (
            float(odds.get("completeness_percentage", 0.0)) < 1.0
            or int(odds.get("missing_odds_count", 0)) > 0
        ):
            blockers.append(BLOCKER_NEEDS_ODDS)
        # Only the legacy manual path treats an absent market as a blocker.
        # API-first excludes it instead; see market_eligibility.
        if provider.get("btts_status") == "Unavailable":
            blockers.append(BLOCKER_NEEDS_BTTS)
        if (
            provider.get("staging_validation_verdict")
            not in {"Ready for handoff", "Not checked"}
            or int(odds.get("invalid_odds_issue_count", 0)) > 0
        ):
            blockers.append(BLOCKER_NEEDS_VALIDATION)

    if provider.get("team_mapping_status") not in {"Verified", "Not checked"}:
        blockers.append(BLOCKER_NEEDS_MAPPING)

    # The provider allowlist remains a hard gate in both modes. Market
    # eligibility narrows *which markets* may be used; it never grants trust.
    if not provider.get("provider_allowed"):
        blockers.append(BLOCKER_PROVIDER_NOT_TRUSTED)

    return list(dict.fromkeys(blockers))


def build_epl_model_task(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """EPL Model routine status: is the model ready and may the card run?"""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    evidence = _gather_evidence(outputs)
    readiness = evidence["week1_readiness"]
    shadow = evidence["provider_shadow"]

    odds = _odds_status(readiness)
    provider = _provider_status(shadow)
    eligibility = _market_eligibility(evidence["automated_card_input"])
    investigation = _market_investigation(evidence["market_discovery"])
    blockers = _collect_blockers(odds, provider, evidence, eligibility)

    card_ready = not blockers
    model_readiness = "Ready" if card_ready else "Blocked"

    if blockers:
        next_action = (
            "Clear the listed blockers before running EPL CARD. Start with "
            f"`{blockers[0]}`: {BLOCKER_REMEDIES.get(blockers[0], 'see the reports for detail.')}"
        )
    else:
        next_action = (
            "All tracked gates pass. Review the evidence manually, then EPL CARD "
            "may run."
        )

    summary: dict[str, Any] = {
        "report": "EPL Model Task",
        "generated_at": _now(now),
        "model_readiness": model_readiness,
        "fixture_freshness": odds["fixture_status"],
        "selected_slate": {
            "window": odds["selected_window"],
            "fixtures_in_window": odds["selected_window_fixture_count"],
            "fixtures_outside_window": odds["fixtures_outside_selected_window_count"],
            "odds_rows_outside_window": odds["odds_rows_outside_selected_window_count"],
            "warnings": odds["slate_warnings"],
        },
        "odds_status": odds,
        "provider_status": provider,
        "mapping_coverage": {
            "status": provider["team_mapping_status"],
            "coverage_percentage": provider["team_mapping_coverage"],
            "unmapped_teams": provider["unmapped_teams"],
        },
        "market_coverage": {
            "core_markets_status": provider["core_market_status"],
            "btts_status": provider["btts_status"],
            "btts_row_count": provider["btts_row_count"],
            "btts_trusted": False,
        },
        "market_eligibility": eligibility,
        "market_investigation": investigation,
        "included_markets": eligibility["included_markets"],
        "excluded_markets": eligibility["excluded_markets"],
        "manual_odds_entry_required": eligibility["manual_entry_required"],
        "blockers": blockers,
        "next_action": next_action,
        "epl_card_ready": card_ready,
        "evidence_errors": [
            message
            for message in (
                evidence["week1_readiness_error"],
                evidence["provider_shadow_error"],
                evidence["staging_validation_error"],
            )
            if message
        ],
        "safety": {
            "official_picks_generated": False,
            "provider_allowlisted": False,
            "protected_files_edited": False,
            "bets_placed": False,
            "settlement_applied": False,
            "cron_enabled": False,
        },
    }
    return summary


def render_epl_model_task(summary: Mapping[str, Any]) -> str:
    slate = summary["selected_slate"]
    odds = summary["odds_status"]
    provider = summary["provider_status"]
    mapping = summary["mapping_coverage"]
    markets = summary["market_coverage"]
    eligible = summary["market_eligibility"]
    investigation = summary["market_investigation"]
    blockers = [f"- {item}" for item in summary["blockers"]] or ["- None."]
    lines = [
        "# EPL Model Task",
        "",
        (
            "Status feed for the **EPL Model** scheduled routine. This report "
            "reads existing evidence only. It generates no picks, runs no "
            "provider, and edits no protected file."
        ),
        "",
        "## Readiness",
        "",
        f"- Model readiness: **{summary['model_readiness']}**",
        f"- Fixture freshness: **{summary['fixture_freshness']}**",
        f"- EPL CARD ready: **{'Yes' if summary['epl_card_ready'] else 'No'}**",
        "",
        "## Selected slate",
        "",
        f"- Window: **{slate['window']}**",
        f"- Fixtures inside window: **{slate['fixtures_in_window']}**",
        f"- Fixtures outside window: **{slate['fixtures_outside_window']}**",
        f"- Odds rows outside window: **{slate['odds_rows_outside_window']}**",
        *[f"- Warning: {item}" for item in slate["warnings"]],
        "",
        "## Odds",
        "",
        f"- Readiness status: **{odds['readiness_status']}**",
        f"- Odds file status: **{odds['odds_file_status']}**",
        f"- Completeness: **{odds['completeness_percentage']:.1%}**",
        f"- Missing odds rows: **{odds['missing_odds_count']}**",
        f"- Validation warnings: **{odds['validation_warning_count']}**",
        "",
        "## Provider / shadow",
        "",
        f"- Shadow verdict: **{provider['verdict']}** ({provider['mode']})",
        f"- Staging validation: **{provider['staging_validation_verdict']}**",
        f"- Handoff eligible: **{'Yes' if provider['handoff_eligible'] else 'No'}**",
        f"- Provider allowed by policy: **{'Yes' if provider['provider_allowed'] else 'No'}**",
        "- Provider odds treated as trusted: **No (shadow only)**",
        "",
        "## Mapping coverage",
        "",
        f"- Status: **{mapping['status']}**",
        (
            "- Coverage: "
            + (
                f"**{float(mapping['coverage_percentage']):.1%}**"
                if mapping["coverage_percentage"] is not None
                else "**Not checked**"
            )
        ),
        f"- Unmapped teams: {mapping['unmapped_teams'] or 'none'}",
        "",
        "## Market coverage",
        "",
        f"- Core markets (1X2 + totals): **{markets['core_markets_status']}**",
        f"- BTTS: **{markets['btts_status']}** ({markets['btts_row_count']} rows)",
        f"- BTTS trusted: **{'Yes' if markets['btts_trusted'] else 'No'}**",
        "",
        "## Market eligibility",
        "",
        f"- Included (usable for picks): **{eligible['included_markets'] or 'none'}**",
        f"- Excluded: **{eligible['excluded_markets'] or 'none'}**",
        f"- Unavailable: {eligible['unavailable_markets'] or 'none'}",
        f"- Incomplete: {eligible['incomplete_markets'] or 'none'}",
        f"- Disabled: {eligible['disabled_markets'] or 'none'}",
        (
            "- Manual odds entry required: "
            f"**{'Yes' if eligible['manual_entry_required'] else 'No'}**"
        ),
        (
            f"- Provider-derived card input: `{eligible['card_input_path'] or 'not built'}` "
            f"({eligible['card_input_row_count']} rows)"
        ),
        "",
        eligible["note"],
        "",
        "## Market investigation",
        "",
        (
            f"- Totals: **{investigation['totals']['status']}** "
            f"({investigation['totals']['events_with_required_line']}/"
            f"{investigation['totals']['events_total']} events with the required line)"
        ),
        f"  - {investigation['totals']['root_cause'] or 'Not investigated yet.'}",
        (
            f"- BTTS: **{investigation['btts']['status']}** "
            f"({investigation['btts']['events_with_btts']}/"
            f"{investigation['btts']['events_total']} events; event endpoint checked: "
            f"{'Yes' if investigation['btts']['checked_event_endpoint'] else 'No'})"
        ),
        f"  - {investigation['btts']['root_cause'] or 'Not investigated yet.'}",
        "",
        investigation["profitability_note"],
        "",
        "## Blockers",
        "",
        *blockers,
        "",
        "## Exact next action",
        "",
        summary["next_action"],
        "",
    ]
    if summary["evidence_errors"]:
        lines.extend(
            [
                "## Missing evidence",
                "",
                *[f"- {item}" for item in summary["evidence_errors"]],
                "",
            ]
        )
    return "\n".join(lines)


def save_epl_model_task(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    summary = build_epl_model_task(output_dir=outputs, now=now)
    paths = _write_pair(
        summary,
        render_epl_model_task(summary),
        outputs,
        json_name=MODEL_TASK_JSON,
        markdown_name=MODEL_TASK_MARKDOWN,
    )
    return {"summary": summary, **paths}


def build_epl_card_task(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """EPL CARD routine status. Refuses to produce picks unless truly ready."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    evidence = _gather_evidence(outputs)
    readiness = evidence["week1_readiness"]
    shadow = evidence["provider_shadow"]

    odds = _odds_status(readiness)
    provider = _provider_status(shadow)
    eligibility = _market_eligibility(evidence["automated_card_input"])
    investigation = _market_investigation(evidence["market_discovery"])
    blockers = _collect_blockers(odds, provider, evidence, eligibility)

    card_ready = not blockers
    card_status = "Ready" if card_ready else "Blocked"

    # The card only carries selections when every gate passes. While blocked it
    # returns empty lists, never placeholders, so a routine cannot mistake an
    # empty card for a produced one.
    generated = evidence["automated_card"]
    card_generated = bool(generated.get("card_generated", False))
    best_bets: list[dict[str, Any]] = []
    leans: list[dict[str, Any]] = []
    passes: list[dict[str, Any]] = []
    unit_suggestions: list[dict[str, Any]] = []

    # Selections are carried only when the gates pass AND a card was actually
    # generated. A blocked card yields empty lists, never placeholders.
    if card_ready and card_generated:
        best_bets = list(generated.get("best_bets", []) or [])
        leans = list(generated.get("leans", []) or [])
        passes = list(generated.get("passes_or_avoids", []) or [])
        unit_suggestions = list(generated.get("unit_suggestions", []) or [])

    if card_ready:
        next_action = (
            "Gates pass. Review the generated card evidence manually before "
            "publishing any selection."
        )
    else:
        next_action = (
            "Do not publish picks. Start with "
            f"`{blockers[0]}`: "
            + BLOCKER_REMEDIES.get(blockers[0], "see the reports for detail.")
            + (
                f" Then: {', '.join(blockers[1:])}."
                if len(blockers) > 1
                else ""
            )
        )

    return {
        "report": "EPL Card Task",
        "generated_at": _now(now),
        "card_status": card_status,
        "card_ready": card_ready,
        "automated_generation_ready": card_ready
        and bool(eligibility.get("card_input_written")),
        "automated_card_generated": card_generated,
        "picks_suppressed": not card_ready,
        "best_bets": best_bets,
        "leans": leans,
        "passes_or_avoids": passes,
        "unit_suggestions": unit_suggestions,
        "market_eligibility": eligibility,
        "market_investigation": investigation,
        "card_scope": (
            "+".join(eligibility["included_markets"]) or "none"
        ),
        "included_markets": eligibility["included_markets"],
        "excluded_markets": eligibility["excluded_markets"],
        "unavailable_markets": eligibility["unavailable_markets"],
        "manual_odds_entry_required": eligibility["manual_entry_required"],
        "excluded_markets_note": (
            "Excluded markets are unavailable, incomplete, or disabled. They are "
            "never presented as passes, avoids, or no-value calls, and no BTTS "
            "pick is produced while BTTS is unavailable."
        ),
        "validation_warnings": odds["slate_warnings"],
        "validation_warning_count": odds["validation_warning_count"],
        "odds_source": (
            "provider-derived automated card input"
            if eligibility.get("card_input_written")
            else "manual current_odds.csv (legacy)"
        ),
        "odds_completeness": {
            # Completeness of the ACTIVE source. In API-first mode that is the
            # provider-derived input, not the manual template.
            "completion_percentage": (
                1.0
                if eligibility.get("card_input_written")
                else odds["completeness_percentage"]
            ),
            "missing_odds_count": (
                0
                if eligibility.get("card_input_written")
                else odds["missing_odds_count"]
            ),
            "status": (
                "Provider-derived input complete for eligible markets"
                if eligibility.get("card_input_written")
                else odds["odds_file_status"]
            ),
            "legacy_manual_template_completion": odds["completeness_percentage"],
            "legacy_manual_template_missing": odds["missing_odds_count"],
            "legacy_template_is_active_source": not bool(
                eligibility.get("card_input_written")
            ),
        },
        "provider_source": {
            "provider_verdict": provider["verdict"],
            "handoff_eligible": provider["handoff_eligible"],
            "provider_allowed": provider["provider_allowed"],
            "source_used": (
                eligibility.get("card_input_path")
                or "none (provider output is shadow-only and untrusted)"
            ),
            "trusted": bool(provider.get("provider_allowed")),
        },
        "blockers": blockers,
        "next_action": next_action,
        "evidence_errors": [
            message
            for message in (
                evidence["week1_readiness_error"],
                evidence["provider_shadow_error"],
            )
            if message
        ],
        "safety": {
            "official_picks_generated": False,
            "picks_invented": False,
            "provider_allowlisted": False,
            "protected_files_edited": False,
            "bets_placed": False,
        },
    }


def render_epl_card_task(summary: Mapping[str, Any]) -> str:
    completeness = summary["odds_completeness"]
    provider = summary["provider_source"]
    blockers = [f"- {item}" for item in summary["blockers"]] or ["- None."]
    lines = [
        "# EPL Card Task",
        "",
        (
            "Status feed for the **EPL CARD** scheduled routine. The card only "
            "carries selections when every gate passes; while blocked it returns "
            "empty lists rather than placeholder picks."
        ),
        "",
        "## Card status",
        "",
        f"- Card status: **{summary['card_status']}**",
        f"- Picks suppressed: **{'Yes' if summary['picks_suppressed'] else 'No'}**",
        "",
        "## Selections",
        "",
    ]
    if summary["card_ready"]:
        lines.extend(
            [
                f"- Best bets: {len(summary['best_bets'])}",
                f"- Leans: {len(summary['leans'])}",
                f"- Passes/avoids: {len(summary['passes_or_avoids'])}",
                f"- Unit suggestions: {len(summary['unit_suggestions'])}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- Best bets: **withheld** (card not ready)",
                "- Leans: **withheld** (card not ready)",
                "- Passes/avoids: **withheld** (card not ready)",
                "- Unit suggestions: **withheld** (card not ready)",
                "",
                (
                    "No pick, lean, or stake was generated. An empty card here "
                    "means blocked, not 'no value found'."
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Markets",
            "",
            f"- Included in the card: **{summary['included_markets'] or 'none'}**",
            f"- Excluded: **{summary['excluded_markets'] or 'none'}**",
            f"- Unavailable: {summary['unavailable_markets'] or 'none'}",
            (
                "- Manual odds entry required: "
                f"**{'Yes' if summary['manual_odds_entry_required'] else 'No'}**"
            ),
            (
                "- Automated generation ready: "
                f"**{'Yes' if summary['automated_generation_ready'] else 'No'}**"
            ),
            "",
            summary["excluded_markets_note"],
            "",
            "## Odds completeness",
            "",
            f"- Completeness: **{completeness['completion_percentage']:.1%}**",
            f"- Missing odds rows: **{completeness['missing_odds_count']}**",
            f"- Odds file status: **{completeness['status']}**",
            "",
            "## Provider / source",
            "",
            f"- Provider shadow verdict: **{provider['provider_verdict']}**",
            f"- Handoff eligible: **{'Yes' if provider['handoff_eligible'] else 'No'}**",
            f"- Provider allowed by policy: **{'Yes' if provider['provider_allowed'] else 'No'}**",
            f"- Source used for picks: **{provider['source_used']}**",
            "",
            "## Validation warnings",
            "",
            *(
                [f"- {item}" for item in summary["validation_warnings"]]
                or ["- None recorded."]
            ),
            "",
            "## Blockers",
            "",
            *blockers,
            "",
            "## Exact next action",
            "",
            summary["next_action"],
            "",
        ]
    )
    if summary["evidence_errors"]:
        lines.extend(
            [
                "## Missing evidence",
                "",
                *[f"- {item}" for item in summary["evidence_errors"]],
                "",
            ]
        )
    return "\n".join(lines)


def save_epl_card_task(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    summary = build_epl_card_task(output_dir=outputs, now=now)
    paths = _write_pair(
        summary,
        render_epl_card_task(summary),
        outputs,
        json_name=CARD_TASK_JSON,
        markdown_name=CARD_TASK_MARKDOWN,
    )
    return {"summary": summary, **paths}


def build_epl_settle_preview_task(
    *,
    output_dir: Path | None = None,
    ledger_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """EPL SETTLE (IGNORE) routine: preview only, never settles.

    The ledger is opened read-only. This function has no write path to it at
    all — there is deliberately no `apply`, `force`, or `settle` parameter.
    """
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    ledger = MANUAL_DIR / "bet_ledger.csv" if ledger_path is None else Path(ledger_path)

    errors: list[str] = []
    frame = pd.DataFrame()
    if not ledger.is_file():
        errors.append(f"Bet ledger not found: `{_relative(ledger)}`.")
    else:
        try:
            frame = pd.read_csv(ledger, dtype=str).fillna("")
        except (OSError, UnicodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
            errors.append(f"Bet ledger could not be read: `{_relative(ledger)}`.")

    total_rows = int(len(frame))
    result_column = "result" if "result" in frame.columns else ""
    if result_column and total_rows:
        results = frame[result_column].astype(str).str.strip()
        open_rows = int((results == "").sum())
        settled_rows = int((results != "").sum())
    else:
        open_rows = 0
        settled_rows = 0

    return {
        "report": "EPL Settle Preview Task",
        "generated_at": _now(now),
        "mode": "Preview only",
        "ledger_path": _relative(ledger),
        "ledger_row_count": total_rows,
        "open_bet_count": open_rows,
        "settled_bet_count": settled_rows,
        "would_settle_count": 0,
        "preview_note": (
            "Preview only. This task never applies settlement, never edits "
            "`bet_ledger.csv`, never uses force mode, and never places a bet."
        ),
        "blockers": list(errors),
        "next_action": (
            "Review open bets manually. Settlement remains a deliberate human "
            "action run from Terminal; this routine will not perform it."
        ),
        "evidence_errors": errors,
        "safety": {
            "settlement_applied": False,
            "ledger_edited": False,
            "force_mode_used": False,
            "bets_placed": False,
            "write_path_exists": False,
        },
        "outputs_dir": str(outputs),
    }


def render_epl_settle_preview_task(summary: Mapping[str, Any]) -> str:
    safety = summary["safety"]
    lines = [
        "# EPL Settle Preview Task",
        "",
        (
            "Status feed for the **EPL SETTLE (IGNORE)** scheduled routine. This "
            "is preview only. It has no code path that writes the ledger."
        ),
        "",
        "## Preview",
        "",
        f"- Mode: **{summary['mode']}**",
        f"- Ledger: `{summary['ledger_path']}`",
        f"- Ledger rows: **{summary['ledger_row_count']}**",
        f"- Open bets: **{summary['open_bet_count']}**",
        f"- Settled bets: **{summary['settled_bet_count']}**",
        f"- Bets this run would settle: **{summary['would_settle_count']}**",
        "",
        "## Safety",
        "",
        f"- Settlement applied: **{'Yes' if safety['settlement_applied'] else 'No'}**",
        f"- Ledger edited: **{'Yes' if safety['ledger_edited'] else 'No'}**",
        f"- Force mode used: **{'Yes' if safety['force_mode_used'] else 'No'}**",
        f"- Bets placed: **{'Yes' if safety['bets_placed'] else 'No'}**",
        "",
        summary["preview_note"],
        "",
        "## Blockers",
        "",
        *([f"- {item}" for item in summary["blockers"]] or ["- None."]),
        "",
        "## Exact next action",
        "",
        summary["next_action"],
        "",
    ]
    return "\n".join(lines)


def save_epl_settle_preview_task(
    *,
    output_dir: Path | None = None,
    ledger_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    summary = build_epl_settle_preview_task(
        output_dir=outputs, ledger_path=ledger_path, now=now
    )
    paths = _write_pair(
        summary,
        render_epl_settle_preview_task(summary),
        outputs,
        json_name=SETTLE_TASK_JSON,
        markdown_name=SETTLE_TASK_MARKDOWN,
    )
    return {"summary": summary, **paths}
