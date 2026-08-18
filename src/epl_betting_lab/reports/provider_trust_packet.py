"""Consolidated provider trust / allowlist approval packet.

The repository already has an acceptance process (archived shadow runs, an
acceptance checklist, evidence bundles, a human acceptance receipt, and a PR
gate). This module does not replace or shortcut any of it. It gathers the
evidence into one packet so the human approval decision has everything in front
of it, and states the exact remaining approval in plain terms.

It cannot and does not edit `staging_provider_policy.json`. Allowlisting stays a
deliberate human action.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.market_eligibility import DEFAULT_DISABLED_MARKETS
from epl_betting_lab.reports.pick_display import format_market_list


PACKET_JSON_FILENAME = "provider_trust_packet.json"
PACKET_MARKDOWN_FILENAME = "provider_trust_packet.md"

PROVIDER_NAME = "the_odds_api"


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, f"Missing report: `{path.name}`."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"Unreadable report `{path.name}`: {type(exc).__name__}."
    return (payload if isinstance(payload, dict) else {}), ""


def _section(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def build_provider_trust_packet(
    *,
    output_dir: Path | None = None,
    policy_path: Path | None = None,
    provider_name: str = PROVIDER_NAME,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    policy_file = (
        MANUAL_DIR / "staging_provider_policy.json"
        if policy_path is None
        else Path(policy_path)
    )

    checklist, checklist_error = _read_json(
        outputs / "provider_acceptance_checklist.json"
    )
    shadow, shadow_error = _read_json(outputs / "provider_shadow_verification.json")
    card_input, card_input_error = _read_json(outputs / "automated_card_input.json")
    policy, policy_error = _read_json(policy_file)

    errors = [
        item
        for item in (checklist_error, shadow_error, card_input_error, policy_error)
        if item
    ]

    allowed_names = policy.get("allowed_provider_names", [])
    allowed_names = allowed_names if isinstance(allowed_names, list) else []
    currently_allowed = provider_name in {_clean(item) for item in allowed_names}

    completed_runs = int(checklist.get("completed_live_run_count", 0) or 0)
    required_runs = int(checklist.get("minimum_required_runs", 3) or 3)
    checklist_verdict = _clean(checklist.get("verdict")) or "Not checked"

    mapping = _section(shadow, "team_mapping")
    quota = _section(shadow, "api_quota")
    safety = _section(shadow, "safety")
    slate = _section(shadow, "slate_coverage")
    btts = _section(shadow, "btts_availability")
    eligibility = _section(card_input, "eligibility")

    # Readiness must not contradict the acceptance checklist. The checklist
    # reviews a window of past runs and fails closed on any that failed, were
    # blocked, or predate a fix, so a raw run count reaching the minimum is not
    # by itself sufficient.
    checklist_ok = checklist_verdict in {"Trusted", "Ready for acceptance"}

    outstanding: list[str] = []
    if completed_runs < required_runs:
        outstanding.append(
            f"Complete {required_runs - completed_runs} more live shadow run(s): "
            f"{completed_runs}/{required_runs} recorded."
        )
    if _clean(mapping.get("status")) != "Verified":
        outstanding.append("Team mapping must report Verified.")
    if not checklist_ok and completed_runs >= required_runs:
        outstanding.append(
            f"Acceptance checklist verdict is `{checklist_verdict}`; resolve its "
            "listed failures. The checklist reviews a window of past runs and "
            "fails closed on any that failed, were blocked, or predate a fix."
        )
    if not currently_allowed:
        outstanding.append(
            f"Explicit human approval to add `{provider_name}` to "
            "`allowed_provider_names` in "
            "`data/manual/staging_provider_policy.json`."
        )

    ready_for_approval = (
        completed_runs >= required_runs
        and _clean(mapping.get("status")) == "Verified"
        and checklist_ok
    )

    return {
        "report": "Provider Trust Packet",
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(
            timespec="seconds"
        ),
        "provider_name": provider_name,
        "currently_allowlisted": currently_allowed,
        "policy_path": str(policy_file),
        "policy_allowed_provider_names": [_clean(item) for item in allowed_names],
        "acceptance": {
            "verdict": checklist_verdict,
            "completed_live_runs": completed_runs,
            "required_live_runs": required_runs,
            "runs_remaining": max(0, required_runs - completed_runs),
        },
        "coverage_summary": {
            "team_mapping_status": _clean(mapping.get("status")) or "Not checked",
            "team_mapping_coverage": mapping.get("coverage_percentage"),
            "unmapped_teams": list(mapping.get("unmapped_teams", []) or []),
            "provider_returned": _section(slate, "provider_returned"),
            "selected_week1_window": _section(slate, "selected_week1_window"),
            "full_upcoming_fixtures": _section(slate, "full_upcoming_fixtures"),
        },
        "market_eligibility_summary": {
            "included_markets": list(eligibility.get("eligible_markets", []) or []),
            "excluded_markets": list(eligibility.get("excluded_markets", []) or []),
            "unavailable_markets": list(
                eligibility.get("unavailable_markets", []) or []
            ),
            "incomplete_markets": list(eligibility.get("incomplete_markets", []) or []),
            "disabled_markets": list(eligibility.get("disabled_markets", []) or [])
            or list(DEFAULT_DISABLED_MARKETS),
            "btts_status": _clean(btts.get("status")) or "Not checked",
            "card_input_rows": int(card_input.get("row_count", 0) or 0),
            "manual_entry_required": bool(
                card_input.get("manual_entry_required", False)
            ),
        },
        "quota_summary": {
            "status": _clean(quota.get("status")) or "Not checked",
            "requests_used": _clean(quota.get("requests_used")),
            "requests_remaining": _clean(quota.get("requests_remaining")),
        },
        "safety_flags": {
            "secrets_written_or_printed": bool(
                safety.get("secrets_written_or_printed", False)
            ),
            "manual_or_production_files_edited": bool(
                safety.get("manual_or_production_files_edited", False)
            ),
            "provider_policy_edited": bool(safety.get("provider_policy_edited", False)),
            "staging_promoted": bool(safety.get("staging_promoted", False)),
            "trusted_picks_generated": bool(
                safety.get("trusted_picks_generated", False)
            ),
            "bets_placed": bool(safety.get("bets_placed", False)),
            "cron_enabled": bool(safety.get("cron_enabled", False)),
        },
        "ready_for_human_approval": ready_for_approval,
        "outstanding_requirements": outstanding,
        "exact_approval_needed": (
            f"Add `\"{provider_name}\"` to `allowed_provider_names` in "
            "`data/manual/staging_provider_policy.json`. This packet does not and "
            "cannot make that edit; it requires your explicit approval."
        ),
        "evidence_errors": errors,
        "safety": {
            "policy_edited": False,
            "provider_allowlisted": False,
            "picks_generated": False,
            "bets_placed": False,
        },
    }


def render_provider_trust_packet(summary: Mapping[str, Any]) -> str:
    acceptance = summary["acceptance"]
    coverage = summary["coverage_summary"]
    markets = summary["market_eligibility_summary"]
    quota = summary["quota_summary"]
    flags = summary["safety_flags"]

    def _scope_row(name: str, scope: Mapping[str, Any]) -> str:
        pct = scope.get("coverage_percentage")
        rendered = f"{float(pct):.1%}" if isinstance(pct, (int, float)) else "n/a"
        return (
            f"| `{name}` | {_clean(scope.get('status')) or 'Not checked'} | "
            f"{scope.get('covered_fixture_count', 0)}/"
            f"{scope.get('expected_fixture_count', 0)} | {rendered} |"
        )

    lines = [
        "# Provider Trust Packet",
        "",
        (
            "Consolidated evidence for the provider allowlist decision. This "
            "report cannot edit policy, allowlist a provider, generate picks, or "
            "place bets."
        ),
        "",
        "## Decision",
        "",
        f"- Provider: **{summary['provider_name']}**",
        f"- Currently allowlisted: **{'Yes' if summary['currently_allowlisted'] else 'No'}**",
        f"- Ready for human approval: **{'Yes' if summary['ready_for_human_approval'] else 'No'}**",
        "",
        "## Acceptance progress",
        "",
        f"- Checklist verdict: **{acceptance['verdict']}**",
        (
            "- Completed live runs: "
            f"**{acceptance['completed_live_runs']}/{acceptance['required_live_runs']}**"
            f" ({acceptance['runs_remaining']} remaining)"
        ),
        "",
        "## Coverage summary",
        "",
        f"- Team mapping: **{coverage['team_mapping_status']}**",
        f"- Unmapped teams: {coverage['unmapped_teams'] or 'none'}",
        "",
        "| Scope | Status | Covered | Coverage |",
        "|:------|:-------|:--------|:---------|",
        _scope_row("provider_returned", coverage["provider_returned"]),
        _scope_row("selected_week1_window", coverage["selected_week1_window"]),
        _scope_row("full_upcoming_fixtures", coverage["full_upcoming_fixtures"]),
        "",
        "## Market eligibility summary",
        "",
        f"- Included: **{format_market_list(markets['included_markets'])}**",
        f"- Excluded: **{format_market_list(markets['excluded_markets'])}**",
        f"- Unavailable: {format_market_list(markets['unavailable_markets'])}",
        f"- Incomplete: {format_market_list(markets['incomplete_markets'])}",
        f"- Disabled: {format_market_list(markets['disabled_markets'])}",
        f"- BTTS: **{markets['btts_status']}**",
        f"- Provider-derived card input rows: **{markets['card_input_rows']}**",
        (
            "- Manual odds entry required: "
            f"**{'Yes' if markets['manual_entry_required'] else 'No'}**"
        ),
        "",
        "## Quota",
        "",
        f"- Status: **{quota['status']}**",
        f"- Used: {quota['requests_used'] or 'n/a'}",
        f"- Remaining: {quota['requests_remaining'] or 'n/a'}",
        "",
        "## Safety flags",
        "",
        *[
            f"- {name.replace('_', ' ').capitalize()}: "
            f"**{'Yes' if value else 'No'}**"
            for name, value in flags.items()
        ],
        "",
        "## Outstanding requirements",
        "",
        *([f"- {item}" for item in summary["outstanding_requirements"]] or ["- None."]),
        "",
        "## Exact approval needed",
        "",
        summary["exact_approval_needed"],
        "",
    ]
    if summary["evidence_errors"]:
        lines.extend(
            ["## Missing evidence", "", *[f"- {e}" for e in summary["evidence_errors"]], ""]
        )
    return "\n".join(lines)


def save_provider_trust_packet(
    *,
    output_dir: Path | None = None,
    policy_path: Path | None = None,
    provider_name: str = PROVIDER_NAME,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    summary = build_provider_trust_packet(
        output_dir=outputs,
        policy_path=policy_path,
        provider_name=provider_name,
        now=now,
    )
    outputs.mkdir(parents=True, exist_ok=True)
    json_path = outputs / PACKET_JSON_FILENAME
    markdown_path = outputs / PACKET_MARKDOWN_FILENAME
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_provider_trust_packet(summary), encoding="utf-8")
    return {"summary": summary, "json": str(json_path), "markdown": str(markdown_path)}
