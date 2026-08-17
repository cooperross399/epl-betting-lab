"""Diagnose why a computed evidence bundle differs from the stored one.

The Provider Policy PR Gate reports only *that* the computed bundle differs
from the verified one, never *how*. That is enough to fail safely and far too
little to fix anything, so a mismatch turns into guesswork against a safety
gate — exactly where guessing is least acceptable.

This module answers the question directly: which files does each side include,
which are missing from one, and which shared files disagree on checksum.

It is diagnostic only. It never rewrites evidence, never relaxes a check, and
never decides whether a gate passes. It emits paths, checksums, and counts —
never file contents — so a report can be attached to a CI run without leaking a
credential or an odds payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from epl_betting_lab.config import OUTPUTS_DIR


BUNDLE_FILENAME = "provider_allowlist_evidence_bundle.json"
VERIFICATION_FILENAME = "provider_allowlist_evidence_bundle_verification.json"
DIAGNOSTIC_JSON_FILENAME = "provider_bundle_diagnostic.json"
DIAGNOSTIC_MARKDOWN_FILENAME = "provider_bundle_diagnostic.md"

#: Only these fields are ever read out of an evidence entry. Contents are not.
SAFE_ENTRY_FIELDS = (
    "evidence_path",
    "evidence_type",
    "status",
    "required",
    "current_checksum_sha256",
    "expected_checksum_sha256",
)


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, f"missing: {path.name}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"unreadable: {path.name} ({type(exc).__name__})"
    return (payload if isinstance(payload, dict) else {}), ""


def _entries(bundle: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Map evidence_path -> safe fields, ordered by path for determinism."""
    found: dict[str, dict[str, str]] = {}
    evidence = bundle.get("evidence")
    if not isinstance(evidence, list):
        return found
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        path = _clean(item.get("evidence_path"))
        if not path:
            continue
        found[path] = {
            field: _clean(item.get(field)) for field in SAFE_ENTRY_FIELDS
        }
    return dict(sorted(found.items()))


def _tracked_paths(repository_root: Path | None = None) -> set[str]:
    """Files git tracks, so the report can say which evidence CI cannot see."""
    import subprocess

    root = repository_root or Path.cwd()
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {
        item for item in result.stdout.decode("utf-8", "ignore").split("\0") if item
    }


def build_bundle_diagnostic(
    *,
    output_dir: Path | None = None,
    repository_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compare the current bundle against the stored verification."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    bundle, bundle_error = _read_json(outputs / BUNDLE_FILENAME)
    verification, verification_error = _read_json(outputs / VERIFICATION_FILENAME)

    computed_id = _clean(bundle.get("bundle_id"))
    computed_checksum = _clean(bundle.get("bundle_checksum_sha256"))
    stored_id = _clean(verification.get("bundle_id"))
    stored_checksum = _clean(verification.get("bundle_checksum_sha256"))

    computed_entries = _entries(bundle)
    stored_bundle_path = _clean(verification.get("bundle_path"))
    stored_bundle: dict[str, Any] = {}
    stored_source_error = ""
    if stored_bundle_path:
        root = repository_root or Path.cwd()
        candidate = Path(stored_bundle_path)
        resolved = candidate if candidate.is_absolute() else root / candidate
        stored_bundle, stored_source_error = _read_json(resolved)
    stored_entries = _entries(stored_bundle)

    computed_paths = set(computed_entries)
    stored_paths = set(stored_entries)
    only_computed = sorted(computed_paths - stored_paths)
    only_stored = sorted(stored_paths - computed_paths)
    shared = sorted(computed_paths & stored_paths)

    checksum_differences = [
        {
            "evidence_path": path,
            "computed_checksum_sha256": computed_entries[path][
                "current_checksum_sha256"
            ],
            "stored_checksum_sha256": stored_entries[path]["current_checksum_sha256"],
        }
        for path in shared
        if computed_entries[path]["current_checksum_sha256"]
        != stored_entries[path]["current_checksum_sha256"]
    ]

    tracked = _tracked_paths(repository_root)
    # The failure mode that keeps recurring: evidence bound by path but never
    # committed, so a clean checkout recomputes the bundle without it.
    untracked_evidence = sorted(
        path for path in computed_paths if tracked and path not in tracked
    )
    untracked_stored_bundle = bool(
        stored_bundle_path and tracked and stored_bundle_path not in tracked
    )

    likely_causes: list[str] = []
    if untracked_evidence:
        likely_causes.append(
            f"{len(untracked_evidence)} evidence file(s) are bound by path but not "
            "tracked by git, so a clean checkout cannot reproduce the bundle."
        )
    if untracked_stored_bundle:
        likely_causes.append(
            "The stored verification binds an archived bundle that is not tracked "
            f"by git: `{stored_bundle_path}`."
        )
    if only_computed:
        likely_causes.append(
            f"{len(only_computed)} file(s) appear only in the computed bundle."
        )
    if only_stored:
        likely_causes.append(
            f"{len(only_stored)} file(s) appear only in the stored bundle."
        )
    if checksum_differences:
        likely_causes.append(
            f"{len(checksum_differences)} shared file(s) differ by checksum."
        )
    if not likely_causes and computed_checksum != stored_checksum:
        likely_causes.append(
            "The bundles list identical files with identical checksums but still "
            "differ, so the difference is in bundle metadata rather than evidence."
        )

    return {
        "report": "Provider Evidence Bundle Diagnostic",
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(
            timespec="seconds"
        ),
        "matches": bool(
            computed_id
            and stored_id
            and computed_id == stored_id
            and computed_checksum == stored_checksum
        ),
        "computed_bundle_id": computed_id,
        "computed_bundle_checksum_sha256": computed_checksum,
        "stored_bundle_id": stored_id,
        "stored_bundle_checksum_sha256": stored_checksum,
        "stored_bundle_path": stored_bundle_path,
        "computed_evidence_count": len(computed_entries),
        "stored_evidence_count": len(stored_entries),
        "computed_evidence": [
            {"evidence_path": path, **fields}
            for path, fields in computed_entries.items()
        ],
        "stored_evidence": [
            {"evidence_path": path, **fields} for path, fields in stored_entries.items()
        ],
        "only_in_computed": only_computed,
        "only_in_stored": only_stored,
        "checksum_differences": checksum_differences,
        "untracked_evidence_paths": untracked_evidence,
        "stored_bundle_is_untracked": untracked_stored_bundle,
        "likely_causes": likely_causes,
        "read_errors": [
            item
            for item in (bundle_error, verification_error, stored_source_error)
            if item
        ],
        "safety": {
            "file_contents_included": False,
            "secrets_included": False,
            "evidence_modified": False,
            "gate_decision_made": False,
        },
    }


def render_bundle_diagnostic(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Provider Evidence Bundle Diagnostic",
        "",
        (
            "Diagnostic only. It compares the computed bundle against the stored "
            "verification and reports paths, checksums, and counts. It never "
            "includes file contents, never modifies evidence, and never decides "
            "whether a gate passes."
        ),
        "",
        f"- Bundles match: **{'Yes' if summary['matches'] else 'No'}**",
        f"- Computed bundle id: `{summary['computed_bundle_id'] or 'none'}`",
        f"- Stored bundle id: `{summary['stored_bundle_id'] or 'none'}`",
        f"- Computed checksum: `{summary['computed_bundle_checksum_sha256'] or 'none'}`",
        f"- Stored checksum: `{summary['stored_bundle_checksum_sha256'] or 'none'}`",
        f"- Stored bundle path: `{summary['stored_bundle_path'] or 'none'}`",
        (
            "- Stored bundle tracked by git: "
            f"**{'No' if summary['stored_bundle_is_untracked'] else 'Yes'}**"
        ),
        f"- Evidence entries: computed **{summary['computed_evidence_count']}**, "
        f"stored **{summary['stored_evidence_count']}**",
        "",
        "## Likely causes",
        "",
        *([f"- {item}" for item in summary["likely_causes"]] or ["- None identified."]),
        "",
    ]

    if summary["untracked_evidence_paths"]:
        lines.extend(
            [
                "## Evidence bound but not tracked by git",
                "",
                "A clean checkout cannot reproduce a bundle that binds these:",
                "",
                *[f"- `{item}`" for item in summary["untracked_evidence_paths"]],
                "",
            ]
        )
    for title, key in (
        ("Only in the computed bundle", "only_in_computed"),
        ("Only in the stored bundle", "only_in_stored"),
    ):
        if summary[key]:
            lines.extend(
                [f"## {title}", "", *[f"- `{item}`" for item in summary[key]], ""]
            )
    if summary["checksum_differences"]:
        lines.extend(
            [
                "## Shared files with differing checksums",
                "",
                "| Evidence path | Computed | Stored |",
                "|:--------------|:---------|:-------|",
                *[
                    f"| `{item['evidence_path']}` | "
                    f"`{item['computed_checksum_sha256'][:16] or 'none'}` | "
                    f"`{item['stored_checksum_sha256'][:16] or 'none'}` |"
                    for item in summary["checksum_differences"]
                ],
                "",
            ]
        )
    if summary["read_errors"]:
        lines.extend(
            ["## Read errors", "", *[f"- {item}" for item in summary["read_errors"]], ""]
        )
    lines.extend(
        [
            "## Safety",
            "",
            "- File contents included: **No**",
            "- Secrets included: **No**",
            "- Evidence modified: **No**",
            "- Gate decision made: **No**",
            "",
        ]
    )
    return "\n".join(lines)


def save_bundle_diagnostic(
    *,
    output_dir: Path | None = None,
    repository_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    summary = build_bundle_diagnostic(
        output_dir=outputs, repository_root=repository_root, now=now
    )
    outputs.mkdir(parents=True, exist_ok=True)
    json_path = outputs / DIAGNOSTIC_JSON_FILENAME
    markdown_path = outputs / DIAGNOSTIC_MARKDOWN_FILENAME
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(render_bundle_diagnostic(summary), encoding="utf-8")
    return {"summary": summary, "json": str(json_path), "markdown": str(markdown_path)}
