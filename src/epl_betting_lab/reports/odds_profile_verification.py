from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.odds_export_profile_diagnostic import (
    read_odds_export_source,
)
from epl_betting_lab.reports.odds_export_profile_suggestion_validation import (
    VALIDATION_COLUMNS,
    VERDICT_READY,
    build_odds_export_profile_suggestion_validation,
)


DEFAULT_REGISTRY_PATH = MANUAL_DIR / "odds_import_profiles.json"
DEFAULT_SOURCE_PATH = MANUAL_DIR / "sportsbook_export.csv"
FATAL_VERIFICATION_STATUSES = {
    "missing_profile",
    "missing_registry",
    "malformed_registry",
    "missing_source",
    "empty_source",
    "unreadable_source",
}


class InstalledOddsProfileVerificationError(RuntimeError):
    """Raised by the dashboard when installed-profile verification cannot run."""


def _empty_summary(
    status: str,
    message: str,
    profile_name: str,
    registry_path: Path,
    source_path: Path,
) -> dict[str, object]:
    return {
        "status": status,
        "verdict": "Verification unavailable",
        "message": message,
        "profile_name": profile_name or "missing",
        "registry_path": str(registry_path),
        "source_path": str(source_path),
        "row_count": 0,
        "valid_rows": 0,
        "invalid_rows": 0,
        "duplicate_rows": 0,
        "draft_issues": [message],
    }


def render_installed_odds_profile_verification(
    preview: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    issues = summary.get("draft_issues", [])
    lines = [
        "# Installed Odds Profile Verification",
        "",
        "This verification reads the installed profile and source export, then converts rows only in memory. "
        "It does not write `current_odds_import.csv`, edit odds, apply imports, or place bets.",
        "",
        f"## Verdict: {summary.get('verdict', 'Verification unavailable')}",
        "",
        f"- Status: {summary.get('status', 'unknown')}",
        f"- Profile: {summary.get('profile_name', 'missing')}",
        f"- Registry: `{summary.get('registry_path', '')}`",
        f"- Source export: `{summary.get('source_path', '')}`",
        f"- Converted rows: {int(summary.get('row_count', 0))}",
        f"- Valid rows: {int(summary.get('valid_rows', 0))}",
        f"- Invalid rows: {int(summary.get('invalid_rows', 0))}",
        f"- Duplicate rows: {int(summary.get('duplicate_rows', 0))}",
        f"- Message: {summary.get('message', '')}",
        "",
        "## Profile and row issues",
        "",
        "\n".join(f"- {issue}" for issue in issues) if issues else "No profile-level issues found.",
        "",
        "## Sample converted rows",
        "",
        preview.head(10).to_markdown(index=False)
        if not preview.empty
        else "No converted sample rows are available.",
        "",
        "## Next step",
        "",
    ]
    if summary.get("status") == "verified":
        lines.append(
            "The installed profile passed this source export check. Continue to use the normal conversion preview; "
            "this is not permission to place bets or bypass import validation."
        )
    elif summary.get("status") == "needs_attention":
        lines.append(
            "Review the installed mapping and source values. Use the rollback preview before restoring a backup."
        )
    else:
        lines.append("Fix the missing or unreadable input, then run verification again.")
    return "\n".join(lines)


def _save_verification(
    preview: pd.DataFrame,
    summary: dict[str, object],
    output_dir: Path,
) -> dict[str, Path | str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "odds_profile_post_install_verification.csv"
    markdown_path = output_dir / "odds_profile_post_install_verification.md"
    preview.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_installed_odds_profile_verification(preview, summary),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "status": str(summary.get("status", "unknown")),
        "verdict": str(summary.get("verdict", "Verification unavailable")),
        "message": str(summary.get("message", "")),
    }


def verify_installed_odds_profile(
    profile_name: str,
    source_path: Path | None = None,
    registry_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path | str]:
    profile_name = profile_name.strip()
    source_path = source_path or DEFAULT_SOURCE_PATH
    registry_path = registry_path or DEFAULT_REGISTRY_PATH
    output_dir = output_dir or OUTPUTS_DIR
    empty = pd.DataFrame(columns=VALIDATION_COLUMNS)

    if not profile_name:
        summary = _empty_summary(
            "missing_profile",
            "A profile name is required. Use `--profile PROFILE_NAME`.",
            profile_name,
            registry_path,
            source_path,
        )
        return _save_verification(empty, summary, output_dir)
    if not registry_path.exists():
        summary = _empty_summary(
            "missing_registry",
            f"Missing profile registry `{registry_path}`.",
            profile_name,
            registry_path,
            source_path,
        )
        return _save_verification(empty, summary, output_dir)
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        summary = _empty_summary(
            "malformed_registry",
            f"The profile registry is unreadable: {exc}",
            profile_name,
            registry_path,
            source_path,
        )
        return _save_verification(empty, summary, output_dir)
    profiles = registry.get("profiles") if isinstance(registry, dict) else None
    if not isinstance(profiles, dict):
        summary = _empty_summary(
            "malformed_registry",
            "The profile registry must contain a `profiles` JSON object.",
            profile_name,
            registry_path,
            source_path,
        )
        return _save_verification(empty, summary, output_dir)
    if profile_name not in profiles:
        summary = _empty_summary(
            "missing_profile",
            f"Profile `{profile_name}` is not installed. Available profiles: {', '.join(sorted(profiles)) or 'none'}.",
            profile_name,
            registry_path,
            source_path,
        )
        return _save_verification(empty, summary, output_dir)

    source, source_status, source_message = read_odds_export_source(source_path)
    if source is None or source_status != "ready":
        summary = _empty_summary(
            source_status,
            source_message,
            profile_name,
            registry_path,
            source_path,
        )
        return _save_verification(empty, summary, output_dir)

    synthetic_suggestion = {
        "profile_name": profile_name,
        "suggested_profile": profiles[profile_name],
        "missing_required_fields": [],
        "field_suggestions": [],
        "review_needed": [],
    }
    preview, summary = build_odds_export_profile_suggestion_validation(
        synthetic_suggestion,
        source,
    )
    ready = summary.get("verdict") == VERDICT_READY
    summary.update(
        {
            "status": "verified" if ready else "needs_attention",
            "verdict": "Installed profile verified" if ready else "Installed profile needs attention",
            "registry_path": str(registry_path),
            "source_path": str(source_path),
        }
    )
    return _save_verification(preview, summary, output_dir)
