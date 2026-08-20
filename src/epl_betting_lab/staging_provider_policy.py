from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROVIDER_TYPES = (
    "manual_upload",
    "sportsbook_export",
    "odds_api",
    "fixture_provider",
    "unknown",
)
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
UNKNOWN_PROVIDER_NAMES = {"", "unknown", "not available", "not_available"}
PROVENANCE_FILE_SPECS = (
    (
        "source_odds",
        "source_files",
        "current_odds",
        "source_current_odds.csv",
        "source odds",
    ),
    (
        "source_fixtures",
        "source_files",
        "upcoming_fixtures",
        "source_upcoming_fixtures.csv",
        "source fixtures",
    ),
    (
        "staging_odds",
        "staging_files",
        "current_odds",
        "current_odds_staging.csv",
        "staging odds",
    ),
    (
        "staging_fixtures",
        "staging_files",
        "upcoming_fixtures",
        "upcoming_fixtures_staging.csv",
        "staging fixtures",
    ),
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_repository_path(path: Path, repository_root: Path) -> str:
    try:
        return path.relative_to(repository_root).as_posix()
    except ValueError:
        return str(path)


def _contains_symlink(path: Path, repository_root: Path) -> bool:
    try:
        relative = path.absolute().relative_to(repository_root)
    except ValueError:
        return False
    current = repository_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _repository_json_path(
    requested_path: Path,
    *,
    repository_root: Path,
    label: str,
    required_parent: Path | None = None,
) -> tuple[Path, str, list[str]]:
    candidate = (
        requested_path
        if requested_path.is_absolute()
        else repository_root / requested_path
    )
    resolved = candidate.resolve(strict=False)
    display_path = display_repository_path(resolved, repository_root)
    blockers: list[str] = []
    try:
        resolved.relative_to(repository_root)
    except ValueError:
        blockers.append(f"{label} must stay inside the repository.")
    if required_parent is not None:
        try:
            resolved.relative_to(required_parent.resolve())
        except ValueError:
            blockers.append(
                f"{label} must stay inside "
                f"`{display_repository_path(required_parent.resolve(), repository_root)}`."
            )
    if resolved.suffix.lower() != ".json":
        blockers.append(f"{label} must use a `.json` file path.")
    if _contains_symlink(candidate, repository_root):
        blockers.append(f"{label} cannot use a symbolic link.")
    return resolved, display_path, blockers


def _read_json_object(path: Path) -> tuple[dict[str, object] | None, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(value, dict):
        return None, "the JSON root must be an object"
    return value, ""


def load_staging_provider_policy(
    policy_path: Path,
    *,
    repository_root: Path,
) -> dict[str, object]:
    """Load the fail-closed provider, age, timezone, and cutoff policy."""
    root = repository_root.resolve()
    resolved, display_path, blockers = _repository_json_path(
        policy_path,
        repository_root=root,
        label="Staging provider policy",
    )
    result: dict[str, object] = {
        "path": display_path,
        "checksum_sha256": "",
        "status": "Policy missing",
        "valid": False,
        "allowed_provider_names": [],
        "allowed_provider_types": [],
        "allowed_markets": None,
        "allow_unknown_providers": False,
        "allow_missing_provenance": False,
        "max_receipt_age_hours": None,
        "max_provider_run_age_hours": None,
        "timezone": "",
        "thursday_cutoff_time": "",
        "blockers": [],
    }
    if blockers:
        result["status"] = "Policy malformed"
        result["blockers"] = blockers
        return result
    if not resolved.exists():
        result["blockers"] = [
            f"Staging provider policy is missing: `{display_path}`."
        ]
        return result
    if not resolved.is_file():
        result["status"] = "Policy malformed"
        result["blockers"] = [
            f"Staging provider policy is not a regular file: `{display_path}`."
        ]
        return result

    payload, read_error = _read_json_object(resolved)
    if payload is None:
        result["status"] = "Policy malformed"
        result["blockers"] = [
            f"Staging provider policy could not be read: {read_error}"
        ]
        return result
    try:
        result["checksum_sha256"] = file_sha256(resolved)
    except OSError as exc:
        result["status"] = "Policy malformed"
        result["blockers"] = [f"Staging provider policy could not be hashed: {exc}"]
        return result

    policy_blockers: list[str] = []
    names_value = payload.get("allowed_provider_names")
    if not isinstance(names_value, list) or not all(
        isinstance(item, str) and item.strip() for item in names_value
    ):
        policy_blockers.append(
            "allowed_provider_names must be a JSON list of non-blank names."
        )
        allowed_names: list[str] = []
    else:
        allowed_names = list(dict.fromkeys(item.strip() for item in names_value))

    types_value = payload.get("allowed_provider_types")
    if not isinstance(types_value, list) or not all(
        isinstance(item, str) and item.strip() in PROVIDER_TYPES
        for item in types_value
    ):
        policy_blockers.append(
            "allowed_provider_types must contain only supported provider types."
        )
        allowed_types: list[str] = []
    else:
        allowed_types = list(dict.fromkeys(item.strip() for item in types_value))

    # Optional per-market allowlist. Absent means "no market restriction", which
    # keeps every existing policy file valid. When present it is the reviewed
    # set of markets an allowlisted provider may supply for automated picks, so
    # a market that later becomes complete cannot join the card without a
    # deliberate policy change.
    markets_value = payload.get("allowed_markets")
    if markets_value is None:
        allowed_markets: list[str] | None = None
    elif not isinstance(markets_value, list) or not all(
        isinstance(item, str) and item.strip() for item in markets_value
    ):
        policy_blockers.append(
            "allowed_markets must be a JSON list of non-blank market keys."
        )
        allowed_markets = []
    else:
        allowed_markets = list(
            dict.fromkeys(item.strip().lower() for item in markets_value)
        )

    allow_unknown = payload.get("allow_unknown_providers")
    if not isinstance(allow_unknown, bool):
        policy_blockers.append("allow_unknown_providers must be true or false.")
        allow_unknown = False

    allow_missing_provenance = payload.get("allow_missing_provenance", False)
    if not isinstance(allow_missing_provenance, bool):
        policy_blockers.append("allow_missing_provenance must be true or false.")
        allow_missing_provenance = False

    age_value = payload.get("max_receipt_age_hours")
    if isinstance(age_value, bool):
        max_age = None
    else:
        try:
            max_age = float(age_value)
        except (TypeError, ValueError):
            max_age = None
    if max_age is None or max_age <= 0:
        policy_blockers.append("max_receipt_age_hours must be a positive number.")

    provider_age_value = payload.get("max_provider_run_age_hours", age_value)
    if isinstance(provider_age_value, bool):
        max_provider_age = None
    else:
        try:
            max_provider_age = float(provider_age_value)
        except (TypeError, ValueError):
            max_provider_age = None
    if max_provider_age is None or max_provider_age <= 0:
        policy_blockers.append(
            "max_provider_run_age_hours must be a positive number."
        )

    timezone_name = str(payload.get("timezone", "")).strip()
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        policy_blockers.append("timezone must be a valid IANA timezone name.")

    cutoff_text = str(payload.get("thursday_cutoff_time", "")).strip()
    if not TIME_PATTERN.fullmatch(cutoff_text):
        policy_blockers.append("thursday_cutoff_time must use 24-hour HH:MM format.")

    result.update(
        {
            "allowed_provider_names": allowed_names,
            "allowed_provider_types": allowed_types,
            "allowed_markets": allowed_markets,
            "allow_unknown_providers": allow_unknown,
            "allow_missing_provenance": allow_missing_provenance,
            "max_receipt_age_hours": max_age,
            "max_provider_run_age_hours": max_provider_age,
            "timezone": timezone_name,
            "thursday_cutoff_time": cutoff_text,
            "blockers": list(dict.fromkeys(policy_blockers)),
        }
    )
    if policy_blockers:
        result["status"] = "Policy malformed"
    else:
        result["status"] = "Policy loaded"
        result["valid"] = True
    return result


def _verify_provenance_file(
    payload: dict[str, object],
    *,
    field_name: str,
    section_name: str,
    entry_name: str,
    expected_filename: str,
    label: str,
    repository_root: Path,
    staging_dir: Path,
) -> dict[str, object]:
    expected_path = (staging_dir / expected_filename).resolve(strict=False)
    expected_display = display_repository_path(expected_path, repository_root)
    result: dict[str, object] = {
        "field_name": field_name,
        "label": label,
        "path": expected_display,
        "declared_path": "",
        "recorded_checksum_sha256": "",
        "current_checksum_sha256": "",
        "status": "Not available",
        "note": "",
        "blocker": "",
    }
    section = payload.get(section_name)
    entry = section.get(entry_name) if isinstance(section, dict) else None
    if not isinstance(entry, dict):
        note = f"Provenance has no checksum entry for {label}."
        result.update({"note": note, "blocker": note})
        return result

    declared_path_text = str(entry.get("path", "")).strip()
    recorded_checksum = str(entry.get("checksum_sha256", "")).strip().lower()
    result["declared_path"] = declared_path_text
    result["recorded_checksum_sha256"] = recorded_checksum
    if not declared_path_text:
        note = f"Provenance does not record a path for {label}."
        result.update({"note": note, "blocker": note})
        return result
    if not SHA256_PATTERN.fullmatch(recorded_checksum):
        note = f"Provenance does not record a valid SHA-256 checksum for {label}."
        result.update({"note": note, "blocker": note})
        return result

    declared_candidate = Path(declared_path_text)
    if ".." in declared_candidate.parts:
        note = f"The provenance path for {label} contains path traversal (`..`)."
        result.update({"note": note, "blocker": note})
        return result
    lexical_path = (
        declared_candidate
        if declared_candidate.is_absolute()
        else repository_root / declared_candidate
    )
    try:
        declared_path = lexical_path.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        note = f"The provenance path for {label} is unreadable: {exc}"
        result.update(
            {"status": "Unreadable file", "note": note, "blocker": note}
        )
        return result
    if declared_path != expected_path:
        note = (
            f"The provenance path for {label} must be `{expected_display}`; "
            f"it declares `{display_repository_path(declared_path, repository_root)}`."
        )
        result.update({"note": note, "blocker": note})
        return result
    if _contains_symlink(lexical_path.absolute(), repository_root):
        note = f"The provenance path for {label} cannot use a symbolic link."
        result.update(
            {"status": "Unreadable file", "note": note, "blocker": note}
        )
        return result
    if not declared_path.exists():
        note = f"The provenance file for {label} is missing: `{expected_display}`."
        result.update({"status": "Missing file", "note": note, "blocker": note})
        return result
    if not declared_path.is_file():
        note = f"The provenance path for {label} is not a readable file."
        result.update(
            {"status": "Unreadable file", "note": note, "blocker": note}
        )
        return result
    try:
        current_checksum = file_sha256(declared_path)
    except OSError as exc:
        note = f"The provenance file for {label} could not be read: {exc}"
        result.update(
            {"status": "Unreadable file", "note": note, "blocker": note}
        )
        return result

    result["current_checksum_sha256"] = current_checksum
    if current_checksum != recorded_checksum:
        changed_notes = {
            "source_odds": "Provider ran, but source odds changed afterward.",
            "source_fixtures": "Provider ran, but source fixtures changed afterward.",
            "staging_odds": "Provider ran, but staging odds changed afterward.",
            "staging_fixtures": (
                "Provider ran, but staging fixtures changed afterward."
            ),
        }
        note = changed_notes[field_name]
        result.update({"status": "Mismatch", "note": note, "blocker": note})
        return result

    result.update(
        {
            "status": "Verified",
            "note": f"Current {label} matches its recorded SHA-256 checksum.",
        }
    )
    return result


def _checksum_pair_status(
    source: dict[str, object],
    staging: dict[str, object],
    *,
    label: str,
) -> tuple[str, str]:
    statuses = {str(source["status"]), str(staging["status"])}
    precedence = ("Unreadable file", "Missing file", "Mismatch", "Not available")
    for status in precedence:
        if status in statuses:
            return status, f"The {label} source/staging pair is not verified."
    if source["current_checksum_sha256"] != staging["current_checksum_sha256"]:
        return "Mismatch", f"The current source and staging {label} checksums differ."
    return "Verified", f"Source and staging {label} match each other."


def load_staging_provenance(
    provenance_path: Path,
    *,
    repository_root: Path,
    staging_dir: Path,
    generated_at: datetime,
) -> dict[str, object]:
    """Read declared staging provenance without changing or inferring its source."""
    root = repository_root.resolve()
    resolved, display_path, blockers = _repository_json_path(
        provenance_path,
        repository_root=root,
        label="Staging provenance",
        required_parent=staging_dir,
    )
    result: dict[str, object] = {
        "provenance_file_path": display_path,
        "provenance_file_checksum_sha256": "",
        "provenance_status": "Missing",
        "provider_name": "",
        "provider_type": "unknown",
        "source_file_path": "",
        "source_checksum_sha256": "",
        "source_checksum_status": "Not available",
        "source_odds_checksum_status": "Not available",
        "source_fixtures_checksum_status": "Not available",
        "staging_odds_checksum_status": "Not available",
        "staging_fixtures_checksum_status": "Not available",
        "odds_checksum_pair_status": "Not available",
        "fixtures_checksum_pair_status": "Not available",
        "checksum_verification": {},
        "provenance_note": "No provenance receipt found.",
        "generated_by": "",
        "provider_generated_at": "",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "notes": "",
        "blockers": [],
        "warnings": [],
    }
    if blockers:
        result["provenance_status"] = "Invalid"
        result["blockers"] = blockers
        result["provenance_note"] = " ".join(blockers)
        return result
    if not resolved.exists():
        result["warnings"] = [
            "No provenance receipt found. Staging is blocked unless the provider "
            "policy explicitly allows missing provenance."
        ]
        return result
    if not resolved.is_file():
        result["provenance_status"] = "Invalid"
        result["blockers"] = [
            f"Staging provenance is not a regular file: `{display_path}`."
        ]
        result["provenance_note"] = str(result["blockers"][0])
        return result

    payload, read_error = _read_json_object(resolved)
    if payload is None:
        result["provenance_status"] = "Invalid"
        result["blockers"] = [f"Staging provenance could not be read: {read_error}"]
        result["provenance_note"] = str(result["blockers"][0])
        return result
    try:
        result["provenance_file_checksum_sha256"] = file_sha256(resolved)
    except OSError as exc:
        result["provenance_status"] = "Invalid"
        result["blockers"] = [f"Staging provenance could not be hashed: {exc}"]
        result["provenance_note"] = str(result["blockers"][0])
        return result

    provider_name = str(payload.get("provider_name", "")).strip()
    provider_type = str(payload.get("provider_type", "unknown")).strip()
    generated_by = str(payload.get("generated_by", "")).strip()
    provider_generated_at = str(payload.get("generated_at", "")).strip()
    notes = str(payload.get("notes", "")).strip()
    provenance_blockers: list[str] = []
    provenance_warnings: list[str] = []
    if provider_type not in PROVIDER_TYPES:
        provenance_blockers.append(
            "provider_type must be manual_upload, sportsbook_export, odds_api, "
            "fixture_provider, or unknown."
        )
        provider_type = "unknown"
    if not generated_by:
        provenance_warnings.append(
            "generated_by is blank. Add the person, provider job, or workflow name."
        )

    verification: dict[str, dict[str, object]] = {}
    for field_name, section_name, entry_name, filename, label in PROVENANCE_FILE_SPECS:
        verification[field_name] = _verify_provenance_file(
            payload,
            field_name=field_name,
            section_name=section_name,
            entry_name=entry_name,
            expected_filename=filename,
            label=label,
            repository_root=root,
            staging_dir=staging_dir.resolve(),
        )
        blocker = str(verification[field_name].get("blocker", ""))
        if blocker:
            provenance_blockers.append(blocker)

    odds_pair_status, odds_pair_note = _checksum_pair_status(
        verification["source_odds"],
        verification["staging_odds"],
        label="odds",
    )
    fixtures_pair_status, fixtures_pair_note = _checksum_pair_status(
        verification["source_fixtures"],
        verification["staging_fixtures"],
        label="fixtures",
    )
    if odds_pair_status == "Mismatch":
        provenance_blockers.append(odds_pair_note)
    if fixtures_pair_status == "Mismatch":
        provenance_blockers.append(fixtures_pair_note)

    failed_notes = [
        str(item["note"])
        for item in verification.values()
        if item["status"] != "Verified"
    ]
    if odds_pair_status != "Verified":
        failed_notes.append(odds_pair_note)
    if fixtures_pair_status != "Verified":
        failed_notes.append(fixtures_pair_note)
    provenance_note = (
        " ".join(dict.fromkeys(failed_notes))
        if failed_notes
        else (
            "All four files match provenance, and both source-to-staging "
            "checksum pairs are verified."
        )
    )
    source_odds = verification["source_odds"]
    source_path_text = str(source_odds["declared_path"])
    source_checksum = str(source_odds["current_checksum_sha256"])
    source_checksum_status = str(source_odds["status"])

    result.update(
        {
            "provenance_status": "Invalid" if provenance_blockers else "Verified",
            "provider_name": provider_name,
            "provider_type": provider_type,
            "source_file_path": source_path_text,
            "source_checksum_sha256": source_checksum,
            "source_checksum_status": source_checksum_status,
            "source_odds_checksum_status": source_odds["status"],
            "source_fixtures_checksum_status": verification["source_fixtures"][
                "status"
            ],
            "staging_odds_checksum_status": verification["staging_odds"]["status"],
            "staging_fixtures_checksum_status": verification["staging_fixtures"][
                "status"
            ],
            "odds_checksum_pair_status": odds_pair_status,
            "fixtures_checksum_pair_status": fixtures_pair_status,
            "checksum_verification": verification,
            "provenance_note": provenance_note,
            "generated_by": generated_by,
            "provider_generated_at": provider_generated_at,
            "notes": notes,
            "blockers": list(dict.fromkeys(provenance_blockers)),
            "warnings": list(dict.fromkeys(provenance_warnings)),
        }
    )
    return result


def receipt_provenance_from_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "provenance_status": str(payload.get("provenance_status", "")).strip(),
        "provenance_note": str(payload.get("provenance_note", "")).strip(),
        "source_odds_checksum_status": str(
            payload.get("source_odds_checksum_status", "Not available")
        ).strip(),
        "source_fixtures_checksum_status": str(
            payload.get("source_fixtures_checksum_status", "Not available")
        ).strip(),
        "staging_odds_checksum_status": str(
            payload.get("staging_odds_checksum_status", "Not available")
        ).strip(),
        "staging_fixtures_checksum_status": str(
            payload.get("staging_fixtures_checksum_status", "Not available")
        ).strip(),
        "odds_checksum_pair_status": str(
            payload.get("odds_checksum_pair_status", "Not available")
        ).strip(),
        "fixtures_checksum_pair_status": str(
            payload.get("fixtures_checksum_pair_status", "Not available")
        ).strip(),
        "provider_name": str(payload.get("provider_name", "")).strip(),
        "provider_type": str(payload.get("provider_type", "unknown")).strip(),
        "source_file_path": str(payload.get("source_file_path", "")).strip(),
        "source_checksum_sha256": str(
            payload.get("source_checksum_sha256", "")
        ).strip(),
        "generated_by": str(payload.get("generated_by", "")).strip(),
        "generated_at": str(payload.get("generated_at", "")).strip(),
        "provider_generated_at": str(
            payload.get("provider_generated_at", "")
        ).strip(),
        "provider_run_age_minutes": payload.get("provider_run_age_minutes"),
        "provider_age_status": str(
            payload.get("provider_age_status", "Not checked")
        ).strip(),
        "provider_age_note": str(payload.get("provider_age_note", "")).strip(),
        "notes": str(payload.get("notes", "")).strip(),
        "blockers": [],
        "warnings": [],
    }


def _parse_aware_timestamp(value: datetime | str) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo is not None else None


def evaluate_provider_run_age(
    policy: dict[str, object],
    provider_generated_at: datetime | str,
    *,
    evaluated_at: datetime,
) -> dict[str, object]:
    """Classify provider provenance age without changing any input files."""
    raw_timestamp = (
        provider_generated_at.isoformat()
        if isinstance(provider_generated_at, datetime)
        else str(provider_generated_at).strip()
    )
    result: dict[str, object] = {
        "provider_generated_at": raw_timestamp,
        "provider_run_age_minutes": None,
        "max_provider_run_age_hours": policy.get("max_provider_run_age_hours"),
        "provider_age_status": "Policy unavailable",
        "provider_age_note": (
            "Provider age could not be checked because the provider policy is "
            "missing or invalid."
        ),
        "fresh": False,
    }
    if policy.get("valid") is not True or policy.get(
        "max_provider_run_age_hours"
    ) is None:
        return result
    if not raw_timestamp:
        result.update(
            {
                "provider_age_status": "Missing",
                "provider_age_note": "No provider timestamp found. Rerun the provider.",
            }
        )
        return result

    provider_timestamp = _parse_aware_timestamp(raw_timestamp)
    if provider_timestamp is None:
        result.update(
            {
                "provider_age_status": "Invalid",
                "provider_age_note": (
                    "Provider generated_at must be a valid timezone-aware timestamp. "
                    "Rerun the provider."
                ),
            }
        )
        return result
    evaluation_timestamp = _parse_aware_timestamp(evaluated_at)
    if evaluation_timestamp is None:
        result["provider_age_note"] = (
            "Provider age could not be checked because the validation clock is not "
            "timezone-aware."
        )
        return result

    age_minutes = (
        evaluation_timestamp.astimezone(ZoneInfo("UTC"))
        - provider_timestamp.astimezone(ZoneInfo("UTC"))
    ).total_seconds() / 60
    result["provider_run_age_minutes"] = round(age_minutes, 3)
    if age_minutes < 0:
        result.update(
            {
                "provider_age_status": "Future timestamp",
                "provider_age_note": (
                    "Provider timestamp is in the future. Check the system clock or "
                    "provenance file."
                ),
            }
        )
        return result

    max_age_hours = float(policy["max_provider_run_age_hours"])
    if age_minutes > max_age_hours * 60:
        result.update(
            {
                "provider_age_status": "Too old",
                "provider_age_note": (
                    "Provider run is too old. Rerun the staging provider before "
                    "validation."
                ),
            }
        )
        return result

    result.update(
        {
            "provider_age_status": "Fresh",
            "provider_age_note": (
                f"Provider run is {age_minutes:.1f} minute(s) old; policy allows "
                f"up to {max_age_hours:g} hour(s)."
            ),
            "fresh": True,
        }
    )
    return result


def evaluate_staging_provider_policy(
    policy: dict[str, object],
    provenance: dict[str, object],
    *,
    receipt_generated_at: datetime | str,
    evaluated_at: datetime,
) -> dict[str, object]:
    """Evaluate provider identity, receipt age, and Thursday cutoff fail-closed."""
    blockers = [str(item) for item in policy.get("blockers", [])]
    blockers.extend(str(item) for item in provenance.get("blockers", []))
    warnings = [str(item) for item in provenance.get("warnings", [])]
    result: dict[str, object] = {
        "policy_path": policy.get("path", ""),
        "policy_checksum_sha256": policy.get("checksum_sha256", ""),
        "policy_load_status": policy.get("status", "Policy missing"),
        "provider_policy_status": "Unknown provider",
        "provider_allowed": False,
        "provider_name": str(provenance.get("provider_name", "")).strip(),
        "provider_type": str(provenance.get("provider_type", "unknown")).strip(),
        "allow_missing_provenance": bool(policy.get("allow_missing_provenance")),
        "max_receipt_age_hours": policy.get("max_receipt_age_hours"),
        "receipt_age_hours": None,
        "receipt_age_status": "Not checked",
        "timezone": policy.get("timezone", ""),
        "thursday_cutoff_time": policy.get("thursday_cutoff_time", ""),
        "cutoff_at": "",
        "cutoff_policy_status": "Not checked",
        "allowed": False,
        "blockers": [],
        "warnings": [],
    }
    if policy.get("valid") is not True:
        result["provider_policy_status"] = str(
            policy.get("status", "Policy missing")
        )
        result["blockers"] = list(dict.fromkeys(blockers))
        return result

    provider_name = str(provenance.get("provider_name", "")).strip()
    provider_type = str(provenance.get("provider_type", "unknown")).strip()
    provenance_status = str(provenance.get("provenance_status", "")).strip()
    missing_provenance_allowed = (
        provenance_status == "Missing"
        and bool(policy.get("allow_missing_provenance"))
    )
    unknown_provider = (
        provider_name.casefold() in UNKNOWN_PROVIDER_NAMES
        or provider_type == "unknown"
    )
    allowed_names = {
        str(item).strip().casefold()
        for item in policy.get("allowed_provider_names", [])
    }
    allowed_types = {
        str(item).strip() for item in policy.get("allowed_provider_types", [])
    }
    if missing_provenance_allowed:
        result["provider_policy_status"] = "Missing provenance allowed"
        provider_allowed = True
        warnings.append(
            "No provenance receipt found, but the staging provider policy "
            "explicitly allows missing provenance. Review this manual exception."
        )
    elif provenance_status == "Missing":
        result["provider_policy_status"] = "Missing provenance blocked"
        provider_allowed = False
        blockers.append(
            "No provenance receipt found. The staging provider policy does not "
            "allow missing provenance."
        )
    elif unknown_provider:
        result["provider_policy_status"] = "Unknown provider"
        provider_allowed = bool(policy.get("allow_unknown_providers")) and (
            provider_type == "unknown" or provider_type in allowed_types
        )
        if not provider_allowed:
            blockers.append(
                "Provider is unknown and the staging provider policy does not allow "
                "unknown providers."
            )
    else:
        provider_allowed = (
            provider_name.casefold() in allowed_names
            and provider_type in allowed_types
        )
        result["provider_policy_status"] = (
            "Provider allowed" if provider_allowed else "Provider not allowed"
        )
        if not provider_allowed:
            blockers.append(
                f"Provider `{provider_name}` with type `{provider_type}` is not allowed "
                "by the staging provider policy."
            )
    result["provider_allowed"] = provider_allowed

    receipt_timestamp = _parse_aware_timestamp(receipt_generated_at)
    evaluation_timestamp = _parse_aware_timestamp(evaluated_at)
    timezone_name = str(policy.get("timezone", ""))
    try:
        policy_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        policy_timezone = None
    if (
        receipt_timestamp is None
        or evaluation_timestamp is None
        or policy_timezone is None
    ):
        blockers.append(
            "Receipt age/cutoff could not be checked because a timezone-aware "
            "timestamp or policy timezone is invalid."
        )
    else:
        age_hours = (
            evaluation_timestamp.astimezone(ZoneInfo("UTC"))
            - receipt_timestamp.astimezone(ZoneInfo("UTC"))
        ).total_seconds() / 3600
        result["receipt_age_hours"] = round(age_hours, 3)
        max_age = float(policy["max_receipt_age_hours"])
        if age_hours < 0:
            result["receipt_age_status"] = "Receipt from future"
            blockers.append("The staging receipt timestamp is in the future.")
        elif age_hours > max_age:
            result["receipt_age_status"] = "Receipt too old"
            blockers.append(
                f"The staging receipt is {age_hours:.2f} hours old; policy allows "
                f"at most {max_age:g} hours."
            )
        else:
            result["receipt_age_status"] = "Within age limit"

        receipt_local = receipt_timestamp.astimezone(policy_timezone)
        cutoff_hour, cutoff_minute = (
            int(part) for part in str(policy["thursday_cutoff_time"]).split(":")
        )
        # The cutoff is a Thursday deadline, so it applies on Thursdays.
        #
        # It used to be measured against "this week's Thursday", computed as
        # today plus (3 - weekday). On Friday, Saturday and Sunday that lands
        # on the Thursday just gone, so a receipt made on any of those days was
        # always after it: every weekend run was blocked by a rule about
        # Thursday. The card is built five days a week and three of them are
        # the matchdays, so this refused the days that matter most while
        # reporting a Thursday policy as the reason.
        THURSDAY = 3
        if receipt_local.weekday() != THURSDAY:
            result["cutoff_at"] = ""
            result["cutoff_policy_status"] = "Not a Thursday"
        else:
            cutoff_at = datetime.combine(
                receipt_local.date(),
                time(cutoff_hour, cutoff_minute),
                tzinfo=policy_timezone,
            )
            result["cutoff_at"] = cutoff_at.isoformat(timespec="minutes")
            if receipt_local <= cutoff_at:
                result["cutoff_policy_status"] = "Before cutoff"
            else:
                result["cutoff_policy_status"] = "After cutoff"
                blockers.append(
                    "The staging receipt was generated after the Thursday "
                    f"automation cutoff of {policy['thursday_cutoff_time']} "
                    f"{timezone_name}."
                )

    result["blockers"] = list(dict.fromkeys(blockers))
    result["warnings"] = list(dict.fromkeys(warnings))
    result["allowed"] = not blockers
    return result
