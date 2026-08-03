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
        "allow_unknown_providers": False,
        "max_receipt_age_hours": None,
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

    allow_unknown = payload.get("allow_unknown_providers")
    if not isinstance(allow_unknown, bool):
        policy_blockers.append("allow_unknown_providers must be true or false.")
        allow_unknown = False

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
            "allow_unknown_providers": allow_unknown,
            "max_receipt_age_hours": max_age,
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
        "generated_by": "",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "notes": "",
        "blockers": [],
        "warnings": [],
    }
    if blockers:
        result["provenance_status"] = "Invalid"
        result["blockers"] = blockers
        return result
    if not resolved.exists():
        result["warnings"] = [
            f"Staging provenance is missing: `{display_path}`. Provider is unknown."
        ]
        return result
    if not resolved.is_file():
        result["provenance_status"] = "Invalid"
        result["blockers"] = [
            f"Staging provenance is not a regular file: `{display_path}`."
        ]
        return result

    payload, read_error = _read_json_object(resolved)
    if payload is None:
        result["provenance_status"] = "Invalid"
        result["blockers"] = [f"Staging provenance could not be read: {read_error}"]
        return result
    try:
        result["provenance_file_checksum_sha256"] = file_sha256(resolved)
    except OSError as exc:
        result["provenance_status"] = "Invalid"
        result["blockers"] = [f"Staging provenance could not be hashed: {exc}"]
        return result

    provider_name = str(payload.get("provider_name", "")).strip()
    provider_type = str(payload.get("provider_type", "unknown")).strip()
    generated_by = str(payload.get("generated_by", "")).strip()
    notes = str(payload.get("notes", "")).strip()
    source_path_text = str(payload.get("source_file_path", "")).strip()
    recorded_source_checksum = str(
        payload.get("source_checksum_sha256", "")
    ).strip().lower()
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

    source_checksum = ""
    source_checksum_status = "Not available"
    if source_path_text:
        source_candidate = Path(source_path_text)
        source_path = (
            source_candidate
            if source_candidate.is_absolute()
            else root / source_candidate
        ).resolve(strict=False)
        source_path_text = display_repository_path(source_path, root)
        try:
            source_path.relative_to(staging_dir.resolve())
        except ValueError:
            provenance_blockers.append(
                "source_file_path must point to a file inside `data/staging`."
            )
        lexical_source_path = (
            source_candidate
            if source_candidate.is_absolute()
            else root / source_candidate
        )
        if _contains_symlink(lexical_source_path, root):
            provenance_blockers.append("source_file_path cannot use a symbolic link.")
        if not source_path.exists() or not source_path.is_file():
            provenance_blockers.append(
                f"Provenance source file is missing or not a file: `{source_path_text}`."
            )
        else:
            try:
                source_checksum = file_sha256(source_path)
            except OSError as exc:
                provenance_blockers.append(
                    f"Provenance source file could not be hashed: {exc}"
                )
            else:
                if recorded_source_checksum:
                    if not SHA256_PATTERN.fullmatch(recorded_source_checksum):
                        provenance_blockers.append(
                            "source_checksum_sha256 must contain 64 hexadecimal characters."
                        )
                        source_checksum_status = "Invalid"
                    elif recorded_source_checksum != source_checksum:
                        provenance_blockers.append(
                            "source_file_path no longer matches source_checksum_sha256."
                        )
                        source_checksum_status = "Mismatch"
                    else:
                        source_checksum_status = "Verified"
                else:
                    source_checksum_status = "Calculated"
    elif recorded_source_checksum:
        if SHA256_PATTERN.fullmatch(recorded_source_checksum):
            source_checksum = recorded_source_checksum
            source_checksum_status = "Recorded only"
            provenance_warnings.append(
                "A source checksum was supplied without source_file_path, so the source "
                "file could not be rechecked."
            )
        else:
            provenance_blockers.append(
                "source_checksum_sha256 must contain 64 hexadecimal characters."
            )
            source_checksum_status = "Invalid"

    result.update(
        {
            "provenance_status": "Invalid" if provenance_blockers else "Loaded",
            "provider_name": provider_name,
            "provider_type": provider_type,
            "source_file_path": source_path_text,
            "source_checksum_sha256": source_checksum,
            "source_checksum_status": source_checksum_status,
            "generated_by": generated_by,
            "notes": notes,
            "blockers": list(dict.fromkeys(provenance_blockers)),
            "warnings": list(dict.fromkeys(provenance_warnings)),
        }
    )
    return result


def receipt_provenance_from_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "provider_name": str(payload.get("provider_name", "")).strip(),
        "provider_type": str(payload.get("provider_type", "unknown")).strip(),
        "source_file_path": str(payload.get("source_file_path", "")).strip(),
        "source_checksum_sha256": str(
            payload.get("source_checksum_sha256", "")
        ).strip(),
        "generated_by": str(payload.get("generated_by", "")).strip(),
        "generated_at": str(payload.get("generated_at", "")).strip(),
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
    if unknown_provider:
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
        thursday_date = receipt_local.date() + timedelta(
            days=3 - receipt_local.weekday()
        )
        cutoff_at = datetime.combine(
            thursday_date,
            time(cutoff_hour, cutoff_minute),
            tzinfo=policy_timezone,
        )
        result["cutoff_at"] = cutoff_at.isoformat(timespec="minutes")
        if receipt_local <= cutoff_at:
            result["cutoff_policy_status"] = "Before cutoff"
        else:
            result["cutoff_policy_status"] = "After cutoff"
            blockers.append(
                "The staging receipt was generated after the Thursday automation "
                f"cutoff of {policy['thursday_cutoff_time']} {timezone_name}."
            )

    result["blockers"] = list(dict.fromkeys(blockers))
    result["warnings"] = list(dict.fromkeys(warnings))
    result["allowed"] = not blockers
    return result
