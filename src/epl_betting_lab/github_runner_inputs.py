from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.data.loaders import load_matches
from epl_betting_lab.reports.current_odds_completeness import (
    build_current_odds_completeness,
)
from epl_betting_lab.reports.current_odds_validation import (
    build_current_odds_validation,
)
from epl_betting_lab.staging_provider_policy import (
    evaluate_provider_run_age,
    evaluate_staging_provider_policy,
    load_staging_provider_policy,
    receipt_provenance_from_payload,
)
from epl_betting_lab.workflow_status import (
    inspect_current_odds_date_freshness,
    inspect_fixture_date_freshness,
)


HANDOFF_JSON_FILENAME = "github_runner_input_handoff.json"
HANDOFF_MARKDOWN_FILENAME = "github_runner_input_handoff.md"
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
READY_STAGING_VERDICT = "Ready for handoff"


@dataclass(frozen=True)
class _PathInspection:
    path: Path
    display_path: str
    path_policy_valid: bool
    available: bool
    checksum_sha256: str
    checksum_status: str
    blockers: tuple[str, ...]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path, repository_root: Path) -> str:
    try:
        value = path.relative_to(repository_root).as_posix()
    except ValueError:
        value = str(path)
    return "".join(
        character if character.isprintable() and character != "`" else "_"
        for character in value
    )


def _contains_symlink(path: Path, repository_root: Path) -> bool:
    try:
        relative = path.relative_to(repository_root)
    except ValueError:
        return False
    current = repository_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _inspect_repository_csv(
    path: Path,
    *,
    label: str,
    repository_root: Path,
    expected_checksum_sha256: str,
) -> _PathInspection:
    raw_text = str(path).strip()
    candidate = path if path.is_absolute() else repository_root / path
    lexical_path = candidate.absolute()
    resolved = candidate.resolve(strict=False)
    display_path = _display_path(resolved, repository_root)
    blockers: list[str] = []
    path_policy_valid = True

    if not raw_text or raw_text == ".":
        blockers.append(f"{label} path is blank.")
        path_policy_valid = False
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        blockers.append(
            f"{label} must be a repository-relative CSV path inside "
            f"`{repository_root}`."
        )
        path_policy_valid = False
    if resolved.suffix.lower() != ".csv":
        blockers.append(f"{label} must point to a `.csv` file.")
        path_policy_valid = False
    if path_policy_valid and _contains_symlink(lexical_path, repository_root):
        blockers.append(
            f"{label} uses a symbolic link. GitHub runner handoff files must be "
            "regular repository files."
        )
        path_policy_valid = False

    available = False
    checksum = ""
    if path_policy_valid:
        if not resolved.exists():
            blockers.append(f"{label} is missing: `{display_path}`.")
        elif not resolved.is_file():
            blockers.append(f"{label} is not a regular file: `{display_path}`.")
        else:
            try:
                checksum = _sha256(resolved)
            except OSError as exc:
                blockers.append(f"{label} could not be read: {exc}")
            else:
                available = True

    expected = expected_checksum_sha256.strip().lower()
    if expected:
        if not SHA256_PATTERN.fullmatch(expected):
            checksum_status = "Invalid expected checksum"
            blockers.append(
                f"The expected SHA-256 value for {label.lower()} must contain "
                "exactly 64 hexadecimal characters."
            )
        elif not checksum:
            checksum_status = "Not available"
        elif checksum == expected:
            checksum_status = "Verified"
        else:
            checksum_status = "Mismatch"
            blockers.append(
                f"{label} checksum does not match the optional checksum entered "
                "when the workflow was started."
            )
    else:
        checksum_status = "Recorded" if checksum else "Not available"

    return _PathInspection(
        path=resolved,
        display_path=display_path,
        path_policy_valid=path_policy_valid,
        available=available,
        checksum_sha256=checksum,
        checksum_status=checksum_status,
        blockers=tuple(blockers),
    )


def _receipt_value(
    payload: dict[str, object],
    section: str,
    field: str,
    default: object = "",
) -> object:
    value = payload.get(section)
    if not isinstance(value, dict):
        return default
    return value.get(field, default)


def _receipt_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _receipt_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _csv_row_count(path: Path) -> tuple[int | None, str]:
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    except (
        OSError,
        UnicodeError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        return None, str(exc)
    return int(len(frame)), ""


def _inspect_staging_receipt(
    staging_receipt_path: Path | None,
    *,
    required: bool,
    repository_root: Path,
    odds: _PathInspection,
    fixtures: _PathInspection,
    provider_policy_path: Path,
    evaluated_at: datetime,
) -> dict[str, object]:
    """Bind selected inputs to a previously reviewed staging receipt."""
    result: dict[str, object] = {
        "required": required,
        "path": "",
        "path_policy_valid": not required,
        "available": False,
        "receipt_checksum_sha256": "",
        "verdict": "Not checked",
        "generated_at": "",
        "binding_status": "Not required" if not required else "Missing",
        "path_match_status": "Not checked",
        "input_checksum_status": "Not checked",
        "current_odds_checksum_status": "Not checked",
        "fixtures_checksum_status": "Not checked",
        "row_count_status": "Not checked",
        "freshness_status": "Not checked",
        "validation_status": "Not checked",
        "completeness_status": "Not checked",
        "recorded_current_odds_path": "",
        "recorded_fixtures_path": "",
        "recorded_current_odds_sha256": "",
        "recorded_fixtures_sha256": "",
        "recorded_current_odds_row_count": None,
        "recorded_fixtures_row_count": None,
        "current_current_odds_row_count": None,
        "current_fixtures_row_count": None,
        "provider_name": "",
        "provider_type": "unknown",
        "source_file_path": "",
        "source_checksum_sha256": "",
        "provider_generated_at": "",
        "recorded_provider_age_status": "Not checked",
        "provider_run_age_minutes": None,
        "provider_age_status": "Not checked",
        "provider_age_note": "",
        "provenance_status": "Not checked",
        "provenance_binding_status": "Not checked",
        "provenance_note": "",
        "source_odds_checksum_status": "Not checked",
        "source_fixtures_checksum_status": "Not checked",
        "staging_odds_provenance_checksum_status": "Not checked",
        "staging_fixtures_provenance_checksum_status": "Not checked",
        "odds_checksum_pair_status": "Not checked",
        "fixtures_checksum_pair_status": "Not checked",
        "generated_by": "",
        "notes": "",
        "provider_policy_path": "",
        "provider_policy_checksum_sha256": "",
        "provider_policy_match_status": "Not checked",
        "provider_policy_status": "Not checked",
        "provider_allowed": False,
        "receipt_age_hours": None,
        "receipt_age_status": "Not checked",
        "provider_policy_timezone": "",
        "thursday_cutoff_time": "",
        "thursday_cutoff_at": "",
        "cutoff_policy_status": "Not checked",
        "blockers": [],
        "warnings": [],
    }
    blockers: list[str] = []
    warnings: list[str] = []
    if staging_receipt_path is None:
        if required:
            blockers.append(
                "A Ready staging validation receipt is required. Run "
                "`python scripts/validate_staging_inputs.py`, review the result, "
                "and pass its JSON receipt path."
            )
        result["blockers"] = blockers
        return result

    raw_text = str(staging_receipt_path).strip()
    candidate = (
        staging_receipt_path
        if staging_receipt_path.is_absolute()
        else repository_root / staging_receipt_path
    )
    lexical_path = candidate.absolute()
    resolved = candidate.resolve(strict=False)
    display_path = _display_path(resolved, repository_root)
    result["path"] = display_path
    path_policy_valid = True
    if not raw_text or raw_text == ".":
        blockers.append("The staging receipt path is blank.")
        path_policy_valid = False
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        blockers.append(
            "The staging receipt must be a repository-relative JSON file inside "
            f"`{repository_root}`."
        )
        path_policy_valid = False
    if resolved.suffix.lower() != ".json":
        blockers.append("The staging receipt must use a `.json` file path.")
        path_policy_valid = False
    if path_policy_valid and _contains_symlink(lexical_path, repository_root):
        blockers.append("The staging receipt cannot use a symbolic link.")
        path_policy_valid = False
    result["path_policy_valid"] = path_policy_valid
    if not path_policy_valid:
        result["binding_status"] = "Invalid"
        result["blockers"] = _dedupe(blockers)
        return result
    if not resolved.exists():
        blockers.append(f"The staging receipt is missing: `{display_path}`.")
        result["binding_status"] = "Missing"
        result["blockers"] = blockers
        return result
    if not resolved.is_file():
        blockers.append(f"The staging receipt is not a regular file: `{display_path}`.")
        result["binding_status"] = "Invalid"
        result["blockers"] = blockers
        return result

    try:
        receipt_checksum = _sha256(resolved)
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        blockers.append(f"The staging receipt could not be read as JSON: {exc}")
        result["binding_status"] = "Invalid"
        result["blockers"] = blockers
        return result
    if not isinstance(payload, dict):
        blockers.append("The staging receipt JSON root must be an object.")
        result["binding_status"] = "Invalid"
        result["blockers"] = blockers
        return result

    result["available"] = True
    result["receipt_checksum_sha256"] = receipt_checksum
    verdict = str(payload.get("verdict", "")).strip()
    generated_at = str(
        payload.get("generated_at") or payload.get("validated_at") or ""
    ).strip()
    result["verdict"] = verdict or "Missing"
    result["generated_at"] = generated_at
    receipt_provenance = receipt_provenance_from_payload(payload)
    result["provider_name"] = receipt_provenance["provider_name"]
    result["provider_type"] = receipt_provenance["provider_type"]
    result["source_file_path"] = receipt_provenance["source_file_path"]
    result["source_checksum_sha256"] = receipt_provenance[
        "source_checksum_sha256"
    ]
    result["provider_generated_at"] = receipt_provenance[
        "provider_generated_at"
    ]
    result["recorded_provider_age_status"] = receipt_provenance[
        "provider_age_status"
    ]
    result["provenance_status"] = receipt_provenance["provenance_status"]
    result["provenance_note"] = receipt_provenance["provenance_note"]
    result["source_odds_checksum_status"] = receipt_provenance[
        "source_odds_checksum_status"
    ]
    result["source_fixtures_checksum_status"] = receipt_provenance[
        "source_fixtures_checksum_status"
    ]
    result["staging_odds_provenance_checksum_status"] = receipt_provenance[
        "staging_odds_checksum_status"
    ]
    result["staging_fixtures_provenance_checksum_status"] = receipt_provenance[
        "staging_fixtures_checksum_status"
    ]
    result["odds_checksum_pair_status"] = receipt_provenance[
        "odds_checksum_pair_status"
    ]
    result["fixtures_checksum_pair_status"] = receipt_provenance[
        "fixtures_checksum_pair_status"
    ]
    result["generated_by"] = receipt_provenance["generated_by"]
    result["notes"] = receipt_provenance["notes"]
    if verdict != READY_STAGING_VERDICT:
        blockers.append(
            "The staging receipt verdict must be `Ready for handoff`; "
            f"the receipt says `{verdict or 'missing'}`."
        )
    if payload.get("handoff_eligible") is not True:
        blockers.append("The staging receipt does not mark these files handoff eligible.")
    if not generated_at:
        blockers.append("The staging receipt is missing its generated_at timestamp.")
    else:
        try:
            datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            blockers.append("The staging receipt generated_at timestamp is invalid.")

    recorded_odds_path = str(
        _receipt_value(payload, "current_odds_staging", "path")
    ).strip()
    recorded_fixtures_path = str(
        _receipt_value(payload, "upcoming_fixtures_staging", "path")
    ).strip()
    result["recorded_current_odds_path"] = recorded_odds_path
    result["recorded_fixtures_path"] = recorded_fixtures_path
    expected_staging_dir = (repository_root / "data" / "staging").resolve()
    selected_paths_are_staging = True
    for selected_path, label in (
        (odds.path, "current odds"),
        (fixtures.path, "upcoming fixtures"),
    ):
        try:
            selected_path.relative_to(expected_staging_dir)
        except ValueError:
            selected_paths_are_staging = False
            blockers.append(
                f"The selected {label} file must be inside `data/staging` when "
                "a staging receipt is required."
            )
    paths_match = (
        selected_paths_are_staging
        and bool(recorded_odds_path)
        and bool(recorded_fixtures_path)
        and recorded_odds_path == odds.display_path
        and recorded_fixtures_path == fixtures.display_path
    )
    result["path_match_status"] = "Verified" if paths_match else "Mismatch"
    if not paths_match:
        blockers.append(
            "The selected odds/fixtures paths do not match the paths recorded in "
            "the staging receipt."
        )

    recorded_odds_checksum = str(
        _receipt_value(payload, "current_odds_staging", "checksum_sha256")
    ).strip().lower()
    recorded_fixtures_checksum = str(
        _receipt_value(payload, "upcoming_fixtures_staging", "checksum_sha256")
    ).strip().lower()
    result["recorded_current_odds_sha256"] = recorded_odds_checksum
    result["recorded_fixtures_sha256"] = recorded_fixtures_checksum

    def checksum_status(recorded: str, current: str, label: str) -> str:
        if not SHA256_PATTERN.fullmatch(recorded):
            blockers.append(f"The staging receipt has no valid SHA-256 for {label}.")
            return "Invalid"
        if not current:
            blockers.append(f"The current {label} checksum is not available.")
            return "Not available"
        if recorded != current.lower():
            blockers.append(
                f"The current {label} checksum does not match the Ready staging "
                "receipt. The file changed after validation."
            )
            return "Mismatch"
        return "Verified"

    odds_checksum_status = checksum_status(
        recorded_odds_checksum,
        odds.checksum_sha256,
        "current odds staging file",
    )
    fixtures_checksum_status = checksum_status(
        recorded_fixtures_checksum,
        fixtures.checksum_sha256,
        "upcoming fixtures staging file",
    )
    result["current_odds_checksum_status"] = odds_checksum_status
    result["fixtures_checksum_status"] = fixtures_checksum_status
    result["input_checksum_status"] = (
        "Verified"
        if odds_checksum_status == fixtures_checksum_status == "Verified"
        else "Mismatch"
        if "Mismatch" in {odds_checksum_status, fixtures_checksum_status}
        else "Invalid"
    )

    recorded_odds_rows = _receipt_int(
        _receipt_value(payload, "current_odds_staging", "row_count", None)
    )
    recorded_fixture_rows = _receipt_int(
        _receipt_value(payload, "upcoming_fixtures_staging", "row_count", None)
    )
    result["recorded_current_odds_row_count"] = recorded_odds_rows
    result["recorded_fixtures_row_count"] = recorded_fixture_rows
    current_odds_rows, odds_row_error = (
        _csv_row_count(odds.path) if odds.available else (None, "input unavailable")
    )
    current_fixture_rows, fixture_row_error = (
        _csv_row_count(fixtures.path)
        if fixtures.available
        else (None, "input unavailable")
    )
    result["current_current_odds_row_count"] = current_odds_rows
    result["current_fixtures_row_count"] = current_fixture_rows
    rows_match = (
        recorded_odds_rows is not None
        and recorded_fixture_rows is not None
        and recorded_odds_rows > 0
        and recorded_fixture_rows > 0
        and recorded_odds_rows == current_odds_rows
        and recorded_fixture_rows == current_fixture_rows
    )
    result["row_count_status"] = "Verified" if rows_match else "Mismatch"
    if not rows_match:
        detail = "; ".join(
            item for item in (odds_row_error, fixture_row_error) if item
        )
        blockers.append(
            "The current staging row counts do not match the Ready receipt."
            + (f" {detail}" if detail else "")
        )

    odds_past = _receipt_int(
        _receipt_value(payload, "current_odds_date_freshness", "past_rows", None)
    )
    odds_future = _receipt_int(
        _receipt_value(
            payload,
            "current_odds_date_freshness",
            "today_or_future_rows",
            None,
        )
    )
    odds_invalid = _receipt_int(
        _receipt_value(
            payload,
            "current_odds_date_freshness",
            "invalid_date_rows",
            None,
        )
    )
    fixtures_past = _receipt_int(
        _receipt_value(payload, "fixture_date_freshness", "past_rows", None)
    )
    fixtures_future = _receipt_int(
        _receipt_value(
            payload,
            "fixture_date_freshness",
            "today_or_future_rows",
            None,
        )
    )
    fixtures_invalid = _receipt_int(
        _receipt_value(
            payload,
            "fixture_date_freshness",
            "invalid_date_rows",
            None,
        )
    )
    freshness_ready = (
        odds_past == 0
        and odds_invalid == 0
        and odds_future is not None
        and odds_future > 0
        and fixtures_past == 0
        and fixtures_invalid == 0
        and fixtures_future is not None
        and fixtures_future > 0
    )
    result["freshness_status"] = "Ready" if freshness_ready else "Blocked"
    if not freshness_ready:
        blockers.append("The staging receipt does not show acceptable input freshness.")

    validation_status = str(
        _receipt_value(payload, "current_odds_validation", "status")
    ).strip()
    validation_serious = _receipt_int(
        _receipt_value(
            payload,
            "current_odds_validation",
            "serious_issue_count",
            None,
        )
    )
    validation_ready = validation_status == "Ready" and validation_serious == 0
    result["validation_status"] = "Ready" if validation_ready else "Blocked"
    if not validation_ready:
        blockers.append("The staging receipt does not show a clean odds validation.")

    completeness_status = str(
        _receipt_value(payload, "odds_completeness", "status")
    ).strip()
    completion_percentage = _receipt_float(
        _receipt_value(
            payload,
            "odds_completeness",
            "completion_percentage",
            None,
        )
    )
    incomplete_matches = _receipt_int(
        _receipt_value(
            payload,
            "odds_completeness",
            "matches_incomplete",
            None,
        )
    )
    completeness_ready = (
        completeness_status == "Complete"
        and completion_percentage is not None
        and completion_percentage >= 1.0
        and incomplete_matches == 0
    )
    result["completeness_status"] = (
        "Complete" if completeness_ready else "Blocked"
    )
    if not completeness_ready:
        blockers.append("The staging receipt does not show 100% odds completeness.")

    receipt_handoff_allowed = _receipt_value(
        payload,
        "handoff_gate",
        "card_generation_allowed",
        False,
    )
    if receipt_handoff_allowed is not True:
        blockers.append("The staging receipt's existing handoff gate did not allow a card.")

    current_provider_policy = load_staging_provider_policy(
        provider_policy_path,
        repository_root=repository_root,
    )
    receipt_policy = payload.get("provider_policy")
    receipt_policy = receipt_policy if isinstance(receipt_policy, dict) else {}
    recorded_policy_path = str(receipt_policy.get("path", "")).strip()
    recorded_policy_checksum = str(
        receipt_policy.get("checksum_sha256", "")
    ).strip().lower()
    current_policy_path = str(current_provider_policy.get("path", "")).strip()
    current_policy_checksum = str(
        current_provider_policy.get("checksum_sha256", "")
    ).strip().lower()
    result["provider_policy_path"] = current_policy_path
    result["provider_policy_checksum_sha256"] = current_policy_checksum
    policy_matches = (
        bool(recorded_policy_path)
        and bool(recorded_policy_checksum)
        and recorded_policy_path == current_policy_path
        and recorded_policy_checksum == current_policy_checksum
    )
    result["provider_policy_match_status"] = (
        "Verified" if policy_matches else "Mismatch"
    )
    if not policy_matches:
        blockers.append(
            "The current staging provider policy path/checksum does not match the "
            "policy recorded in the Ready receipt. Validate staging again."
        )
    if receipt_policy.get("allowed") is not True:
        blockers.append("The staging receipt did not pass its provider policy checks.")

    provider_policy_result = evaluate_staging_provider_policy(
        current_provider_policy,
        receipt_provenance,
        receipt_generated_at=generated_at,
        evaluated_at=evaluated_at,
    )
    result["provider_policy_status"] = provider_policy_result[
        "provider_policy_status"
    ]
    result["provider_allowed"] = provider_policy_result["provider_allowed"]
    result["receipt_age_hours"] = provider_policy_result["receipt_age_hours"]
    result["receipt_age_status"] = provider_policy_result[
        "receipt_age_status"
    ]
    result["provider_policy_timezone"] = provider_policy_result["timezone"]
    result["thursday_cutoff_time"] = provider_policy_result[
        "thursday_cutoff_time"
    ]
    result["thursday_cutoff_at"] = provider_policy_result["cutoff_at"]
    result["cutoff_policy_status"] = provider_policy_result[
        "cutoff_policy_status"
    ]
    blockers.extend(str(item) for item in provider_policy_result["blockers"])
    warnings.extend(str(item) for item in provider_policy_result["warnings"])

    provider_age_result = evaluate_provider_run_age(
        current_provider_policy,
        str(receipt_provenance["provider_generated_at"]),
        evaluated_at=evaluated_at,
    )
    result["provider_run_age_minutes"] = provider_age_result[
        "provider_run_age_minutes"
    ]
    result["provider_age_status"] = provider_age_result["provider_age_status"]
    result["provider_age_note"] = provider_age_result["provider_age_note"]
    if receipt_provenance["provider_age_status"] != "Fresh":
        blockers.append(
            "The staging receipt does not record a Fresh provider run. Validate "
            "staging again after rerunning the provider."
        )
    if provider_age_result["provider_age_status"] != "Fresh":
        blockers.append(str(provider_age_result["provider_age_note"]))

    proof_statuses = (
        result["source_odds_checksum_status"],
        result["source_fixtures_checksum_status"],
        result["staging_odds_provenance_checksum_status"],
        result["staging_fixtures_provenance_checksum_status"],
        result["odds_checksum_pair_status"],
        result["fixtures_checksum_pair_status"],
    )
    provenance_verified = (
        result["provenance_status"] == "Verified"
        and all(status == "Verified" for status in proof_statuses)
    )
    missing_provenance_allowed = (
        result["provenance_status"] == "Missing"
        and bool(current_provider_policy.get("allow_missing_provenance"))
    )
    if provenance_verified:
        result["provenance_binding_status"] = "Verified"
    elif missing_provenance_allowed:
        result["provenance_binding_status"] = "Missing provenance allowed"
        warnings.append(
            "The staging receipt has no provider checksum proof, but the current "
            "policy explicitly allows missing provenance. Review this exception."
        )
    else:
        result["provenance_binding_status"] = "Blocked"
        blockers.append(
            "The Ready staging receipt does not contain verified source-to-staging "
            "checksum proof. Validate staging again after running the provider."
        )

    receipt_warning_count = _receipt_int(payload.get("warning_count")) or 0
    if receipt_warning_count:
        warnings.append(
            f"The Ready staging receipt contains {receipt_warning_count} warning(s). "
            "Review them before trusting the card."
        )

    result["blockers"] = _dedupe(blockers)
    result["warnings"] = _dedupe(warnings)
    result["binding_status"] = "Verified" if not blockers else "Blocked"
    return result


def _issue_codes(issues: pd.DataFrame, severity: str) -> list[str]:
    if issues.empty or not {"severity", "issue"}.issubset(issues.columns):
        return []
    selected = issues[
        issues["severity"].fillna("").astype(str).str.lower() == severity
    ]
    return list(dict.fromkeys(selected["issue"].dropna().astype(str).tolist()))


def build_github_runner_input_handoff(
    *,
    current_odds_path: Path,
    fixtures_path: Path,
    matches_path: Path,
    run_at: datetime,
    repository_root: Path | None = None,
    expected_current_odds_sha256: str = "",
    expected_fixtures_sha256: str = "",
    staging_receipt_path: Path | None = None,
    require_staging_receipt: bool = False,
    staging_provider_policy_path: Path | None = None,
    github_repository: str | None = None,
    github_ref: str | None = None,
    github_sha: str | None = None,
    eligible_markets: Sequence[str] | None = None,
    github_run_id: str | None = None,
) -> dict[str, object]:
    """Inspect committed runner inputs without changing either input file."""
    root = (repository_root or PROJECT_ROOT).resolve()
    odds = _inspect_repository_csv(
        current_odds_path,
        label="Current odds input",
        repository_root=root,
        expected_checksum_sha256=expected_current_odds_sha256,
    )
    fixtures = _inspect_repository_csv(
        fixtures_path,
        label="Upcoming fixtures input",
        repository_root=root,
        expected_checksum_sha256=expected_fixtures_sha256,
    )
    blockers = list(odds.blockers) + list(fixtures.blockers)
    warnings: list[str] = []
    staging_receipt = _inspect_staging_receipt(
        staging_receipt_path,
        required=require_staging_receipt,
        repository_root=root,
        odds=odds,
        fixtures=fixtures,
        provider_policy_path=(
            staging_provider_policy_path
            or root / "data" / "manual" / "staging_provider_policy.json"
        ),
        evaluated_at=run_at,
    )
    blockers.extend(str(item) for item in staging_receipt["blockers"])
    warnings.extend(str(item) for item in staging_receipt["warnings"])

    odds_freshness = None
    if odds.available:
        odds_freshness = inspect_current_odds_date_freshness(
            odds.path,
            today=run_at.date(),
        )
        if odds_freshness.status != "Fresh":
            blockers.append(f"Current odds freshness: {odds_freshness.note}")
        if (odds_freshness.past_rows or 0) > 0:
            blockers.append(
                f"Current odds contain {odds_freshness.past_rows} row(s) tied "
                "to past matches. Remove or archive them before the GitHub run."
            )
        if (odds_freshness.today_or_future_rows or 0) == 0:
            blockers.append(
                "Current odds do not contain any rows for today or a future match."
            )
        if (odds_freshness.invalid_date_rows or 0) > 0:
            blockers.append(
                f"Current odds contain {odds_freshness.invalid_date_rows} blank "
                "or malformed date row(s)."
            )

    fixture_freshness = None
    if fixtures.available:
        fixture_freshness = inspect_fixture_date_freshness(
            fixtures.path,
            today=run_at.date(),
        )
        if fixture_freshness.status != "Fresh":
            blockers.append(f"Fixture freshness: {fixture_freshness.note}")
        if (fixture_freshness.past_fixtures or 0) > 0:
            blockers.append(
                f"Upcoming fixtures contain {fixture_freshness.past_fixtures} "
                "past match row(s). Use a clean upcoming slate for the GitHub run."
            )
        if (fixture_freshness.today_or_future_fixtures or 0) == 0:
            blockers.append(
                "Upcoming fixtures do not contain any match today or in the future."
            )
        if (fixture_freshness.invalid_fixture_dates or 0) > 0:
            blockers.append(
                f"Upcoming fixtures contain "
                f"{fixture_freshness.invalid_fixture_dates} blank or malformed "
                "date row(s)."
            )

    fixture_rows = pd.DataFrame()
    fixture_read_error = ""
    if fixtures.available:
        try:
            fixture_rows = pd.read_csv(fixtures.path, dtype=str)
        except (
            OSError,
            UnicodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
        ) as exc:
            fixture_read_error = str(exc)
            blockers.append(f"Upcoming fixtures CSV could not be read: {exc}")

    matches = pd.DataFrame()
    try:
        matches = load_matches(matches_path)
    except (FileNotFoundError, OSError, UnicodeError, pd.errors.ParserError) as exc:
        warnings.append(
            f"Historical results were unavailable during input handoff validation: {exc}"
        )

    validation_status = "Not checked"
    validation_serious_count = 0
    validation_warning_count = 0
    validation_issue_codes: list[str] = []
    if odds.available and fixtures.available and not fixture_read_error:
        try:
            validation_issues = build_current_odds_validation(
                odds.path,
                matches=matches,
                fixtures=fixture_rows,
            )
        except (
            OSError,
            UnicodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
            ValueError,
        ) as exc:
            validation_status = "Blocked"
            blockers.append(f"Current odds validation could not run: {exc}")
        else:
            validation_warning_count = int(
                (
                    validation_issues["severity"]
                    .fillna("")
                    .astype(str)
                    .str.lower()
                    == "warning"
                ).sum()
            ) if not validation_issues.empty else 0
            serious_rows = int(
                (
                    validation_issues["severity"]
                    .fillna("")
                    .astype(str)
                    .str.lower()
                    == "error"
                ).sum()
            ) if not validation_issues.empty else 0
            validation_serious_count = serious_rows
            validation_issue_codes = _issue_codes(validation_issues, "error")
            validation_status = "Blocked" if serious_rows else "Ready"
            if serious_rows:
                blockers.append(
                    f"Current odds validation found {serious_rows} serious "
                    f"issue(s): {', '.join(validation_issue_codes)}."
                )
            if validation_warning_count:
                warnings.append(
                    f"Current odds validation found {validation_warning_count} "
                    "warning(s). Review them before trusting the card."
                )

    completeness_status = "Not checked"
    completion_percentage = 0.0
    incomplete_matches = 0
    completeness_error_count = 0
    completeness_warning_count = 0
    completeness_issue_codes: list[str] = []
    if odds.available and fixtures.available and not fixture_read_error:
        try:
            completeness_issues, completeness_summary = (
                build_current_odds_completeness(
                    odds.path,
                    fixtures=fixture_rows,
                    eligible_markets=eligible_markets,
                )
            )
        except (
            OSError,
            UnicodeError,
            pd.errors.EmptyDataError,
            pd.errors.ParserError,
            ValueError,
        ) as exc:
            completeness_status = "Blocked"
            blockers.append(f"Odds completeness could not be checked: {exc}")
        else:
            completion_percentage = float(
                completeness_summary.get("completion_percentage", 0.0)
            )
            incomplete_matches = int(
                completeness_summary.get("matches_incomplete", 0)
            )
            if completeness_issues.empty:
                error_mask = pd.Series(dtype=bool)
                warning_mask = pd.Series(dtype=bool)
            else:
                severities = (
                    completeness_issues["severity"]
                    .fillna("")
                    .astype(str)
                    .str.lower()
                )
                error_mask = severities == "error"
                warning_mask = severities == "warning"
            completeness_error_count = int(error_mask.sum())
            completeness_warning_count = int(warning_mask.sum())
            completeness_issue_codes = _issue_codes(completeness_issues, "error")
            complete = (
                completeness_error_count == 0
                and completion_percentage >= 1.0
                and incomplete_matches == 0
            )
            completeness_status = "Complete" if complete else "Blocked"
            if not complete:
                scope = (
                    f" for eligible market(s) {sorted(eligible_markets)}"
                    if eligible_markets is not None
                    else ""
                )
                blockers.append(
                    f"Odds entry is incomplete{scope}: "
                    f"{completion_percentage:.1%} complete, "
                    f"{incomplete_matches} incomplete match(es), and "
                    f"{completeness_error_count} serious completeness issue(s)."
                )
            if completeness_warning_count:
                warnings.append(
                    f"Odds completeness found {completeness_warning_count} "
                    "warning(s)."
                )

    blockers = _dedupe(blockers)
    warnings = _dedupe(warnings)
    card_generation_allowed = not blockers
    if blockers:
        status = "Blocked"
    elif warnings:
        status = "Warnings only"
    else:
        status = "Ready"

    return {
        "run_timestamp": run_at.isoformat(timespec="seconds"),
        "status": status,
        "source_mode": (
            "Ready staging validation receipt"
            if require_staging_receipt
            else "workflow_dispatch repository files"
        ),
        "repository_root": str(root),
        "github_repository": github_repository
        if github_repository is not None
        else os.getenv("GITHUB_REPOSITORY", ""),
        "github_ref": github_ref if github_ref is not None else os.getenv("GITHUB_REF", ""),
        "github_sha": github_sha if github_sha is not None else os.getenv("GITHUB_SHA", ""),
        "github_run_id": github_run_id
        if github_run_id is not None
        else os.getenv("GITHUB_RUN_ID", ""),
        "staging_receipt_required": require_staging_receipt,
        "staging_receipt_path": staging_receipt["path"],
        "staging_receipt_path_policy_valid": staging_receipt[
            "path_policy_valid"
        ],
        "staging_receipt_available": staging_receipt["available"],
        "staging_receipt_checksum_sha256": staging_receipt[
            "receipt_checksum_sha256"
        ],
        "staging_receipt_verdict": staging_receipt["verdict"],
        "staging_receipt_generated_at": staging_receipt["generated_at"],
        "staging_receipt_binding_status": staging_receipt["binding_status"],
        "staging_receipt_path_match_status": staging_receipt[
            "path_match_status"
        ],
        "staging_receipt_input_checksum_status": staging_receipt[
            "input_checksum_status"
        ],
        "staging_receipt_current_odds_checksum_status": staging_receipt[
            "current_odds_checksum_status"
        ],
        "staging_receipt_fixtures_checksum_status": staging_receipt[
            "fixtures_checksum_status"
        ],
        "staging_receipt_row_count_status": staging_receipt[
            "row_count_status"
        ],
        "staging_receipt_freshness_status": staging_receipt[
            "freshness_status"
        ],
        "staging_receipt_validation_status": staging_receipt[
            "validation_status"
        ],
        "staging_receipt_completeness_status": staging_receipt[
            "completeness_status"
        ],
        "staging_receipt_recorded_current_odds_path": staging_receipt[
            "recorded_current_odds_path"
        ],
        "staging_receipt_recorded_fixtures_path": staging_receipt[
            "recorded_fixtures_path"
        ],
        "staging_receipt_recorded_current_odds_sha256": staging_receipt[
            "recorded_current_odds_sha256"
        ],
        "staging_receipt_recorded_fixtures_sha256": staging_receipt[
            "recorded_fixtures_sha256"
        ],
        "staging_receipt_recorded_current_odds_row_count": staging_receipt[
            "recorded_current_odds_row_count"
        ],
        "staging_receipt_recorded_fixtures_row_count": staging_receipt[
            "recorded_fixtures_row_count"
        ],
        "staging_receipt_current_current_odds_row_count": staging_receipt[
            "current_current_odds_row_count"
        ],
        "staging_receipt_current_fixtures_row_count": staging_receipt[
            "current_fixtures_row_count"
        ],
        "staging_receipt_provider_name": staging_receipt["provider_name"],
        "staging_receipt_provider_type": staging_receipt["provider_type"],
        "staging_receipt_source_file_path": staging_receipt[
            "source_file_path"
        ],
        "staging_receipt_source_checksum_sha256": staging_receipt[
            "source_checksum_sha256"
        ],
        "staging_receipt_provider_generated_at": staging_receipt[
            "provider_generated_at"
        ],
        "staging_receipt_recorded_provider_age_status": staging_receipt[
            "recorded_provider_age_status"
        ],
        "staging_receipt_provider_run_age_minutes": staging_receipt[
            "provider_run_age_minutes"
        ],
        "staging_receipt_provider_age_status": staging_receipt[
            "provider_age_status"
        ],
        "staging_receipt_provider_age_note": staging_receipt[
            "provider_age_note"
        ],
        "staging_receipt_provenance_status": staging_receipt[
            "provenance_status"
        ],
        "staging_receipt_provenance_binding_status": staging_receipt[
            "provenance_binding_status"
        ],
        "staging_receipt_provenance_note": staging_receipt["provenance_note"],
        "staging_receipt_source_odds_checksum_status": staging_receipt[
            "source_odds_checksum_status"
        ],
        "staging_receipt_source_fixtures_checksum_status": staging_receipt[
            "source_fixtures_checksum_status"
        ],
        "staging_receipt_staging_odds_provenance_checksum_status": staging_receipt[
            "staging_odds_provenance_checksum_status"
        ],
        "staging_receipt_staging_fixtures_provenance_checksum_status": staging_receipt[
            "staging_fixtures_provenance_checksum_status"
        ],
        "staging_receipt_odds_checksum_pair_status": staging_receipt[
            "odds_checksum_pair_status"
        ],
        "staging_receipt_fixtures_checksum_pair_status": staging_receipt[
            "fixtures_checksum_pair_status"
        ],
        "staging_receipt_generated_by": staging_receipt["generated_by"],
        "staging_receipt_notes": staging_receipt["notes"],
        "staging_provider_policy_path": staging_receipt[
            "provider_policy_path"
        ],
        "staging_provider_policy_checksum_sha256": staging_receipt[
            "provider_policy_checksum_sha256"
        ],
        "staging_provider_policy_match_status": staging_receipt[
            "provider_policy_match_status"
        ],
        "staging_provider_policy_status": staging_receipt[
            "provider_policy_status"
        ],
        "staging_provider_allowed": staging_receipt["provider_allowed"],
        "staging_receipt_age_hours": staging_receipt["receipt_age_hours"],
        "staging_receipt_age_status": staging_receipt["receipt_age_status"],
        "staging_provider_policy_timezone": staging_receipt[
            "provider_policy_timezone"
        ],
        "staging_thursday_cutoff_time": staging_receipt[
            "thursday_cutoff_time"
        ],
        "staging_thursday_cutoff_at": staging_receipt[
            "thursday_cutoff_at"
        ],
        "staging_cutoff_policy_status": staging_receipt[
            "cutoff_policy_status"
        ],
        "current_odds_path": odds.display_path,
        "current_odds_checksum_sha256": odds.checksum_sha256,
        "current_odds_expected_checksum_sha256": (
            expected_current_odds_sha256.strip().lower()
        ),
        "current_odds_checksum_status": odds.checksum_status,
        "current_odds_path_policy_valid": odds.path_policy_valid,
        "current_odds_freshness_status": (
            odds_freshness.status if odds_freshness is not None else "Not checked"
        ),
        "current_odds_freshness_note": (
            odds_freshness.note if odds_freshness is not None else ""
        ),
        "current_odds_earliest_date": (
            odds_freshness.earliest_date if odds_freshness is not None else ""
        ),
        "current_odds_latest_date": (
            odds_freshness.latest_date if odds_freshness is not None else ""
        ),
        "current_odds_past_rows": (
            odds_freshness.past_rows if odds_freshness is not None else None
        ),
        "current_odds_today_or_future_rows": (
            odds_freshness.today_or_future_rows
            if odds_freshness is not None
            else None
        ),
        "current_odds_invalid_date_rows": (
            odds_freshness.invalid_date_rows if odds_freshness is not None else None
        ),
        "fixtures_path": fixtures.display_path,
        "fixtures_checksum_sha256": fixtures.checksum_sha256,
        "fixtures_expected_checksum_sha256": expected_fixtures_sha256.strip().lower(),
        "fixtures_checksum_status": fixtures.checksum_status,
        "fixtures_path_policy_valid": fixtures.path_policy_valid,
        "fixtures_freshness_status": (
            fixture_freshness.status
            if fixture_freshness is not None
            else "Not checked"
        ),
        "fixtures_freshness_note": (
            fixture_freshness.note if fixture_freshness is not None else ""
        ),
        "fixtures_earliest_date": (
            fixture_freshness.earliest_date
            if fixture_freshness is not None
            else ""
        ),
        "fixtures_latest_date": (
            fixture_freshness.latest_date if fixture_freshness is not None else ""
        ),
        "fixtures_past_rows": (
            fixture_freshness.past_fixtures
            if fixture_freshness is not None
            else None
        ),
        "fixtures_today_or_future_rows": (
            fixture_freshness.today_or_future_fixtures
            if fixture_freshness is not None
            else None
        ),
        "fixtures_invalid_date_rows": (
            fixture_freshness.invalid_fixture_dates
            if fixture_freshness is not None
            else None
        ),
        "validation_status": validation_status,
        "validation_serious_issue_count": validation_serious_count,
        "validation_warning_count": validation_warning_count,
        "validation_issue_codes": validation_issue_codes,
        "completeness_status": completeness_status,
        "completion_percentage": completion_percentage,
        "incomplete_match_count": incomplete_matches,
        "completeness_error_count": completeness_error_count,
        "completeness_warning_count": completeness_warning_count,
        "completeness_issue_codes": completeness_issue_codes,
        "card_generation_allowed": card_generation_allowed,
        "blockers": blockers,
        "warnings": warnings,
    }


def render_github_runner_input_handoff(summary: dict[str, object]) -> str:
    allowed = "Yes" if summary["card_generation_allowed"] else "No"
    lines = [
        "# GitHub Runner Odds and Fixtures Handoff",
        "",
        (
            "This receipt proves which committed repository files the manual GitHub "
            "runner inspected. It reads inputs and writes reports only; it does not "
            "create sportsbook prices, edit manual files, or place bets."
        ),
        "",
        "## Gate result",
        "",
        f"- Status: **{summary['status']}**",
        f"- Thursday card generation allowed: **{allowed}**",
        f"- Run timestamp: {summary['run_timestamp']}",
        f"- Input method: {summary['source_mode']}",
        f"- GitHub ref: `{summary['github_ref'] or 'not available'}`",
        f"- GitHub commit: `{summary['github_sha'] or 'not available'}`",
        "",
        "## Staging receipt binding",
        "",
        (
            "- Required: "
            f"**{'Yes' if summary.get('staging_receipt_required') else 'No'}**"
        ),
        (
            "- Receipt path: "
            f"`{summary.get('staging_receipt_path') or 'not provided'}`"
        ),
        (
            "- Receipt verdict: "
            f"**{summary.get('staging_receipt_verdict', 'Not checked')}**"
        ),
        (
            "- Receipt generated at: "
            f"{summary.get('staging_receipt_generated_at') or 'not available'}"
        ),
        (
            "- Receipt binding: "
            f"**{summary.get('staging_receipt_binding_status', 'Not checked')}**"
        ),
        (
            "- Selected path match: "
            f"**{summary.get('staging_receipt_path_match_status', 'Not checked')}**"
        ),
        (
            "- Input checksum match: "
            f"**{summary.get('staging_receipt_input_checksum_status', 'Not checked')}**"
        ),
        (
            "- Row count match: "
            f"**{summary.get('staging_receipt_row_count_status', 'Not checked')}**"
        ),
        (
            "- Provider: "
            f"**{summary.get('staging_receipt_provider_name') or 'unknown'}** "
            f"({summary.get('staging_receipt_provider_type', 'unknown')})"
        ),
        (
            "- Provider policy: "
            f"**{summary.get('staging_provider_policy_status', 'Not checked')}**"
        ),
        (
            "- Provider checksum proof: "
            f"**{summary.get('staging_receipt_provenance_binding_status', 'Not checked')}**"
        ),
        (
            "- Provider run age: "
            f"**{summary.get('staging_receipt_provider_age_status', 'Not checked')}** "
            f"({summary.get('staging_receipt_provider_run_age_minutes')} minute(s); "
            f"generated {summary.get('staging_receipt_provider_generated_at') or 'not available'})"
        ),
        (
            "- Source odds / fixtures: "
            f"**{summary.get('staging_receipt_source_odds_checksum_status', 'Not checked')}** / "
            f"**{summary.get('staging_receipt_source_fixtures_checksum_status', 'Not checked')}**"
        ),
        (
            "- Staging odds / fixtures: "
            f"**{summary.get('staging_receipt_staging_odds_provenance_checksum_status', 'Not checked')}** / "
            f"**{summary.get('staging_receipt_staging_fixtures_provenance_checksum_status', 'Not checked')}**"
        ),
        (
            "- Source-to-staging odds / fixtures pairs: "
            f"**{summary.get('staging_receipt_odds_checksum_pair_status', 'Not checked')}** / "
            f"**{summary.get('staging_receipt_fixtures_checksum_pair_status', 'Not checked')}**"
        ),
        (
            "- Provider policy snapshot match: "
            f"**{summary.get('staging_provider_policy_match_status', 'Not checked')}**"
        ),
        (
            "- Receipt age: "
            f"**{summary.get('staging_receipt_age_status', 'Not checked')}** "
            f"({summary.get('staging_receipt_age_hours')} hour(s))"
        ),
        (
            "- Thursday cutoff: "
            f"**{summary.get('staging_cutoff_policy_status', 'Not checked')}** "
            f"({summary.get('staging_thursday_cutoff_at') or 'not available'})"
        ),
        "",
        "## Input proof",
        "",
        "| Input | Repository path | SHA-256 | Checksum status | Date freshness |",
        "|---|---|---|---|---|",
        (
            f"| Current odds | `{summary['current_odds_path']}` | "
            f"`{summary['current_odds_checksum_sha256'] or 'not available'}` | "
            f"{summary['current_odds_checksum_status']} | "
            f"{summary['current_odds_freshness_status']} |"
        ),
        (
            f"| Upcoming fixtures | `{summary['fixtures_path']}` | "
            f"`{summary['fixtures_checksum_sha256'] or 'not available'}` | "
            f"{summary['fixtures_checksum_status']} | "
            f"{summary['fixtures_freshness_status']} |"
        ),
        "",
        "## Validation gates",
        "",
        f"- Current odds validation: **{summary['validation_status']}**",
        (
            "- Serious validation issues: "
            f"{summary['validation_serious_issue_count']}"
        ),
        f"- Validation warnings: {summary['validation_warning_count']}",
        f"- Odds completeness: **{summary['completeness_status']}**",
        f"- Completion percentage: {float(summary['completion_percentage']):.1%}",
        f"- Incomplete matches: {summary['incomplete_match_count']}",
        "",
        "## Blockers",
        "",
    ]
    blockers = list(summary["blockers"])
    lines.extend([f"- {item}" for item in blockers] or ["- None."])
    lines.extend(["", "## Warnings", ""])
    warnings = list(summary["warnings"])
    lines.extend([f"- {item}" for item in warnings] or ["- None."])
    lines.extend(
        [
            "",
            "## Beginner next step",
            "",
            (
                "If this receipt is Blocked, update the committed odds or fixture "
                "input on the selected branch, run local validation, and start the "
                "manual Action again. Never fill missing odds with guesses."
                if blockers
                else (
                    "The input handoff passed. Review any warnings and the generated "
                    "Thursday reports manually before considering a bet."
                )
            ),
        ]
    )
    return "\n".join(lines)


def save_github_runner_input_handoff(
    *,
    output_dir: Path,
    current_odds_path: Path,
    fixtures_path: Path,
    matches_path: Path,
    run_at: datetime,
    repository_root: Path | None = None,
    expected_current_odds_sha256: str = "",
    expected_fixtures_sha256: str = "",
    staging_receipt_path: Path | None = None,
    require_staging_receipt: bool = False,
    staging_provider_policy_path: Path | None = None,
) -> dict[str, object]:
    summary = build_github_runner_input_handoff(
        current_odds_path=current_odds_path,
        fixtures_path=fixtures_path,
        matches_path=matches_path,
        run_at=run_at,
        repository_root=repository_root,
        expected_current_odds_sha256=expected_current_odds_sha256,
        expected_fixtures_sha256=expected_fixtures_sha256,
        staging_receipt_path=staging_receipt_path,
        require_staging_receipt=require_staging_receipt,
        staging_provider_policy_path=staging_provider_policy_path,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / HANDOFF_JSON_FILENAME
    markdown_path = output_dir / HANDOFF_MARKDOWN_FILENAME
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_github_runner_input_handoff(summary),
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "json": json_path,
        "markdown": markdown_path,
    }
