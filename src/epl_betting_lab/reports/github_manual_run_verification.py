from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR


HANDOFF_JSON_FILENAME = "github_runner_input_handoff.json"
HANDOFF_MARKDOWN_FILENAME = "github_runner_input_handoff.md"
SCHEDULED_JSON_FILENAME = "scheduled_thursday_workflow_summary.json"
SCHEDULED_MARKDOWN_FILENAME = "scheduled_thursday_workflow_summary.md"
VERIFICATION_CSV_FILENAME = "github_manual_thursday_run_verification.csv"
VERIFICATION_MARKDOWN_FILENAME = "github_manual_thursday_run_verification.md"

VERDICTS = (
    "Verified ready run",
    "Verified blocked run",
    "Incomplete run artifacts",
    "Missing handoff proof",
    "Missing scheduled workflow summary",
    "Failed/untrusted run",
)
VERIFICATION_COLUMNS = [
    "category",
    "check",
    "status",
    "expected",
    "actual",
    "details",
]
TRUSTED_HANDOFF_FIELDS = (
    "status",
    "github_ref",
    "github_sha",
    "current_odds_path",
    "current_odds_checksum_sha256",
    "fixtures_path",
    "fixtures_checksum_sha256",
    "current_odds_freshness_status",
    "fixtures_freshness_status",
    "validation_status",
    "completion_percentage",
    "completeness_status",
    "card_generation_allowed",
)
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _load_json(path: Path) -> tuple[dict[str, object] | None, str]:
    if not path.exists():
        return None, "missing"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"unreadable: {exc}"
    if not isinstance(value, dict):
        return None, "invalid: the JSON root must be an object"
    return value, "available"


def _add_check(
    rows: list[dict[str, object]],
    category: str,
    check: str,
    status: str,
    expected: object = "",
    actual: object = "",
    details: str = "",
) -> None:
    rows.append(
        {
            "category": category,
            "check": check,
            "status": status,
            "expected": expected,
            "actual": actual,
            "details": details,
        }
    )


def _display_output_path(path: Path, output_dir: Path) -> str:
    try:
        relative = path.resolve(strict=False).relative_to(output_dir.resolve())
    except ValueError:
        return str(path)
    return f"data/outputs/{relative.as_posix()}"


def _map_output_reference(reference: object, output_dir: Path) -> Path | None:
    text = str(reference or "").strip().replace("\\", "/")
    if not text:
        return None

    raw_path = Path(text)
    if raw_path.is_absolute():
        try:
            relative = raw_path.resolve(strict=False).relative_to(output_dir.resolve())
        except ValueError:
            marker = "/data/outputs/"
            if marker not in text:
                return None
            relative = Path(text.split(marker, 1)[1])
    elif text.startswith("data/outputs/"):
        relative = Path(text.removeprefix("data/outputs/"))
    elif text.startswith("outputs/"):
        relative = Path(text.removeprefix("outputs/"))
    else:
        relative = raw_path

    candidate = (output_dir / relative).resolve(strict=False)
    try:
        candidate.relative_to(output_dir.resolve())
    except ValueError:
        return None
    return candidate


def _step_status(summary: dict[str, object], step_name: str) -> str:
    steps = summary.get("steps", [])
    if not isinstance(steps, list):
        return "Missing"
    for step in steps:
        if isinstance(step, dict) and step.get("step") == step_name:
            return str(step.get("status", "Missing"))
    return "Missing"


def _same_value(field: str, first: object, second: object) -> bool:
    if field == "completion_percentage":
        try:
            return math.isclose(float(first), float(second), abs_tol=1e-9)
        except (TypeError, ValueError):
            return False
    return first == second


def _next_step(verdict: str) -> str:
    return {
        "Verified ready run": (
            "Review the Thursday card, warnings, and prices manually. This verification "
            "does not confirm or place a bet."
        ),
        "Verified blocked run": (
            "The safety gate worked. Fix the listed odds or fixture blockers, prepare a "
            "new committed input branch, and run the manual Action again without force."
        ),
        "Incomplete run artifacts": (
            "Download the complete GitHub artifact again and inspect the Action logs. Do "
            "not trust the card until every expected file is present."
        ),
        "Missing handoff proof": (
            "Rerun the latest Manual Thursday Workflow. The run cannot be trusted without "
            "github_runner_input_handoff.json."
        ),
        "Missing scheduled workflow summary": (
            "Inspect the GitHub Action logs and rerun it. The result cannot be verified "
            "without scheduled_thursday_workflow_summary.json."
        ),
        "Failed/untrusted run": (
            "Do not trust or use recommendations from this run. Review the failed checks "
            "and Action logs, correct the evidence mismatch, and rerun the workflow."
        ),
    }[verdict]


def build_github_manual_run_verification(
    output_dir: Path | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Cross-check a downloaded/manual Thursday artifact without changing its inputs."""
    outputs = (output_dir or OUTPUTS_DIR).resolve()
    handoff_json_path = outputs / HANDOFF_JSON_FILENAME
    scheduled_json_path = outputs / SCHEDULED_JSON_FILENAME
    handoff_markdown_path = outputs / HANDOFF_MARKDOWN_FILENAME
    scheduled_markdown_path = outputs / SCHEDULED_MARKDOWN_FILENAME

    rows: list[dict[str, object]] = []
    trust_failures: list[str] = []
    handoff, handoff_state = _load_json(handoff_json_path)
    scheduled, scheduled_state = _load_json(scheduled_json_path)

    _add_check(
        rows,
        "Evidence",
        "Handoff proof JSON",
        "Pass" if handoff_state == "available" else "Missing" if handoff_state == "missing" else "Fail",
        "Readable JSON object",
        handoff_state,
        str(handoff_json_path),
    )
    _add_check(
        rows,
        "Evidence",
        "Scheduled workflow summary JSON",
        "Pass" if scheduled_state == "available" else "Missing" if scheduled_state == "missing" else "Fail",
        "Readable JSON object",
        scheduled_state,
        str(scheduled_json_path),
    )
    for label, path in (
        ("Handoff proof Markdown", handoff_markdown_path),
        ("Scheduled workflow summary Markdown", scheduled_markdown_path),
    ):
        _add_check(
            rows,
            "Evidence",
            label,
            "Pass" if path.exists() else "Missing",
            "File present",
            "Present" if path.exists() else "Missing",
            str(path),
        )

    if handoff_state == "missing":
        verdict = "Missing handoff proof"
    elif scheduled_state == "missing":
        verdict = "Missing scheduled workflow summary"
    elif handoff is None or scheduled is None:
        verdict = "Failed/untrusted run"
    else:
        verdict = ""

    handoff = handoff or {}
    scheduled = scheduled or {}
    embedded_handoff = scheduled.get("input_handoff")
    if handoff and scheduled:
        if not isinstance(embedded_handoff, dict):
            trust_failures.append(
                "The scheduled summary does not contain its embedded input handoff proof."
            )
            _add_check(
                rows,
                "Consistency",
                "Embedded handoff proof",
                "Fail",
                "Matching handoff object",
                type(embedded_handoff).__name__,
                trust_failures[-1],
            )
        else:
            for field in TRUSTED_HANDOFF_FIELDS:
                standalone_value = handoff.get(field)
                embedded_value = embedded_handoff.get(field)
                matches = _same_value(field, standalone_value, embedded_value)
                if not matches:
                    trust_failures.append(
                        f"Handoff field `{field}` differs between the standalone and "
                        "scheduled receipts."
                    )
                _add_check(
                    rows,
                    "Consistency",
                    f"Handoff {field}",
                    "Pass" if matches else "Fail",
                    standalone_value,
                    embedded_value,
                    "Standalone handoff must match the copy embedded in the scheduled summary.",
                )

    github_ref = str(handoff.get("github_ref", ""))
    github_sha = str(handoff.get("github_sha", ""))
    odds_path = str(handoff.get("current_odds_path", ""))
    odds_checksum = str(handoff.get("current_odds_checksum_sha256", ""))
    fixtures_path = str(handoff.get("fixtures_path", ""))
    fixtures_checksum = str(handoff.get("fixtures_checksum_sha256", ""))
    odds_freshness = str(handoff.get("current_odds_freshness_status", "Not checked"))
    fixtures_freshness = str(handoff.get("fixtures_freshness_status", "Not checked"))
    validation_status = str(handoff.get("validation_status", "Not checked"))
    completeness_status = str(handoff.get("completeness_status", "Not checked"))
    try:
        completion_percentage = float(handoff.get("completion_percentage", 0.0))
    except (TypeError, ValueError):
        completion_percentage = 0.0
        trust_failures.append("The handoff completion percentage is not numeric.")
    card_allowed = handoff.get("card_generation_allowed")
    scheduled_status = str(scheduled.get("status", "Missing"))
    card_step_status = _step_status(scheduled, "Thursday best-bets generation")
    card_generated = card_step_status in {"Completed", "Completed with warnings"}

    proof_values = (
        ("Git ref", github_ref),
        ("Git SHA", github_sha),
        ("Odds path", odds_path),
        ("Odds checksum", odds_checksum),
        ("Fixtures path", fixtures_path),
        ("Fixtures checksum", fixtures_checksum),
        ("Odds freshness", odds_freshness),
        ("Fixtures freshness", fixtures_freshness),
        ("Validation status", validation_status),
        ("Completeness status", completeness_status),
        ("Completion percentage", f"{completion_percentage:.1%}"),
        ("Card generation allowed", card_allowed),
        ("Scheduled workflow status", scheduled_status),
        ("Thursday card step", card_step_status),
    )
    for label, value in proof_values:
        _add_check(rows, "Run summary", label, "Info", "", value)

    if handoff and scheduled:
        proof_requirements = {
            "Git ref": bool(github_ref),
            "Git SHA": bool(GIT_SHA_PATTERN.fullmatch(github_sha.lower())),
            "Odds path": bool(odds_path),
            "Fixtures path": bool(fixtures_path),
            "Handoff status": str(handoff.get("status", ""))
            in {"Ready", "Warnings only", "Blocked"},
            "Scheduled workflow status": scheduled_status
            in {"Ready", "Warnings only", "Blocked", "Partial"},
        }
        for label, passed in proof_requirements.items():
            if not passed:
                trust_failures.append(f"{label} is missing or invalid.")
            _add_check(
                rows,
                "Provenance",
                label,
                "Pass" if passed else "Fail",
                "Present and valid",
                "Present and valid" if passed else "Missing or invalid",
            )

        if not isinstance(card_allowed, bool):
            trust_failures.append("Card generation allowed must be a true/false value.")
        elif card_allowed:
            ready_requirements = {
                "Odds freshness": odds_freshness == "Fresh",
                "Fixtures freshness": fixtures_freshness == "Fresh",
                "Validation": validation_status == "Ready",
                "Completeness status": completeness_status == "Complete",
                "Completeness percentage": completion_percentage >= 1.0,
                "Odds checksum": bool(SHA256_PATTERN.fullmatch(odds_checksum.lower())),
                "Fixtures checksum": bool(
                    SHA256_PATTERN.fullmatch(fixtures_checksum.lower())
                ),
            }
            for label, passed in ready_requirements.items():
                if not passed:
                    trust_failures.append(
                        f"The handoff allowed card generation even though {label.lower()} did not pass."
                    )
                _add_check(
                    rows,
                    "Safety gate",
                    label,
                    "Pass" if passed else "Fail",
                    "Pass",
                    "Pass" if passed else "Did not pass",
                )
            if scheduled_status == "Blocked":
                trust_failures.append(
                    "The handoff allowed the card, but the scheduled workflow reports Blocked."
                )
            if card_step_status in {"Failed", "Blocked"}:
                trust_failures.append(
                    f"Thursday card generation ended with status {card_step_status}."
                )
        else:
            if str(handoff.get("status", "")) != "Blocked":
                trust_failures.append(
                    "Card generation was denied, but the handoff status is not Blocked."
                )
            if scheduled_status != "Blocked":
                trust_failures.append(
                    "The handoff blocked card generation, but the scheduled workflow is not Blocked."
                )
            if card_generated:
                trust_failures.append(
                    "The Thursday card was generated even though the input handoff denied it."
                )

        if scheduled_status == "Failed":
            trust_failures.append("The scheduled Thursday workflow reported Failed.")

    expected_paths: list[Path] = [
        handoff_json_path,
        handoff_markdown_path,
        scheduled_json_path,
        scheduled_markdown_path,
    ]
    output_references = scheduled.get("output_files_created", [])
    if output_references and not isinstance(output_references, list):
        trust_failures.append("Scheduled output_files_created must be a list.")
        output_references = []
    for reference in output_references if isinstance(output_references, list) else []:
        mapped = _map_output_reference(reference, outputs)
        if mapped is None:
            trust_failures.append(
                f"Scheduled output reference could not be mapped safely: {reference}"
            )
        else:
            expected_paths.append(mapped)

    if card_allowed is True:
        expected_paths.extend(
            [outputs / "thursday_best_bets.csv", outputs / "thursday_best_bets.md"]
        )

    unique_expected: list[Path] = []
    seen_paths: set[Path] = set()
    for path in expected_paths:
        resolved = path.resolve(strict=False)
        if resolved not in seen_paths:
            seen_paths.add(resolved)
            unique_expected.append(resolved)

    found_paths = [path for path in unique_expected if path.exists()]
    missing_paths = [path for path in unique_expected if not path.exists()]
    for path in unique_expected:
        _add_check(
            rows,
            "Outputs",
            _display_output_path(path, outputs),
            "Pass" if path.exists() else "Missing",
            "File present",
            "Present" if path.exists() else "Missing",
        )

    if not verdict:
        if trust_failures:
            verdict = "Failed/untrusted run"
        elif missing_paths:
            verdict = "Incomplete run artifacts"
        elif card_allowed is False:
            verdict = "Verified blocked run"
        elif card_allowed is True and card_generated:
            verdict = "Verified ready run"
        elif card_allowed is True:
            verdict = "Incomplete run artifacts"
        else:
            verdict = "Failed/untrusted run"

    if verdict not in VERDICTS:
        raise ValueError(f"Unexpected GitHub manual run verdict: {verdict}")

    verdict_status = (
        "Pass"
        if verdict == "Verified ready run"
        else "Warning"
        if verdict == "Verified blocked run"
        else "Fail"
    )
    rows.insert(
        0,
        {
            "category": "Verdict",
            "check": "Manual Thursday run verification",
            "status": verdict_status,
            "expected": "Verified ready run or Verified blocked run",
            "actual": verdict,
            "details": _next_step(verdict),
        },
    )

    blockers = _dedupe(
        _string_list(handoff.get("blockers"))
        + _string_list(scheduled.get("key_blockers"))
    )
    warnings = _dedupe(
        _string_list(handoff.get("warnings"))
        + _string_list(scheduled.get("key_warnings"))
    )
    summary = {
        "verdict": verdict,
        "next_step": _next_step(verdict),
        "github_ref": github_ref,
        "github_sha": github_sha,
        "current_odds_path": odds_path,
        "current_odds_checksum_sha256": odds_checksum,
        "fixtures_path": fixtures_path,
        "fixtures_checksum_sha256": fixtures_checksum,
        "current_odds_freshness_status": odds_freshness,
        "fixtures_freshness_status": fixtures_freshness,
        "validation_status": validation_status,
        "completion_percentage": completion_percentage,
        "completeness_status": completeness_status,
        "card_generation_allowed": card_allowed,
        "scheduled_workflow_status": scheduled_status,
        "card_generation_step_status": card_step_status,
        "expected_outputs": [
            _display_output_path(path, outputs) for path in unique_expected
        ],
        "found_outputs": [_display_output_path(path, outputs) for path in found_paths],
        "missing_outputs": [
            _display_output_path(path, outputs) for path in missing_paths
        ],
        "key_blockers": blockers,
        "key_warnings": warnings,
        "trust_failures": _dedupe(trust_failures),
    }
    return pd.DataFrame(rows, columns=VERIFICATION_COLUMNS), summary


def render_github_manual_run_verification(
    checks: pd.DataFrame,
    summary: dict[str, object],
) -> str:
    expected = list(summary["expected_outputs"])
    found = list(summary["found_outputs"])
    missing = list(summary["missing_outputs"])
    blockers = list(summary["key_blockers"])
    warnings = list(summary["key_warnings"])
    trust_failures = list(summary["trust_failures"])
    lines = [
        "# GitHub Manual Thursday Run Verification",
        "",
        (
            "This read-only report cross-checks the GitHub runner handoff receipt, "
            "scheduled workflow summary, and claimed output files. It does not edit "
            "odds, fixtures, imports, the ledger, profiles, or model logic; fabricate "
            "prices; or place bets."
        ),
        "",
        "## Verdict",
        "",
        f"- **{summary['verdict']}**",
        f"- Next step: {summary['next_step']}",
        "",
        "## Input proof",
        "",
        f"- Git ref: `{summary['github_ref'] or 'not available'}`",
        f"- Git SHA: `{summary['github_sha'] or 'not available'}`",
        f"- Odds path: `{summary['current_odds_path'] or 'not available'}`",
        (
            "- Odds SHA-256: "
            f"`{summary['current_odds_checksum_sha256'] or 'not available'}`"
        ),
        f"- Fixtures path: `{summary['fixtures_path'] or 'not available'}`",
        (
            "- Fixtures SHA-256: "
            f"`{summary['fixtures_checksum_sha256'] or 'not available'}`"
        ),
        "",
        "## Gate and workflow status",
        "",
        f"- Odds freshness: **{summary['current_odds_freshness_status']}**",
        f"- Fixture freshness: **{summary['fixtures_freshness_status']}**",
        f"- Current odds validation: **{summary['validation_status']}**",
        f"- Odds completeness: **{summary['completeness_status']}**",
        f"- Completion percentage: {float(summary['completion_percentage']):.1%}",
        (
            "- Card generation allowed: **"
            f"{'Yes' if summary['card_generation_allowed'] is True else 'No' if summary['card_generation_allowed'] is False else 'Not available'}**"
        ),
        f"- Scheduled workflow status: **{summary['scheduled_workflow_status']}**",
        f"- Thursday card step: **{summary['card_generation_step_status']}**",
        "",
        "## Output coverage",
        "",
        f"- Expected files: {len(expected)}",
        f"- Files found: {len(found)}",
        f"- Files missing: {len(missing)}",
        "",
        "### Expected outputs",
        "",
    ]
    lines.extend([f"- `{path}`" for path in expected] or ["- None identified."])
    lines.extend(["", "### Found outputs", ""])
    lines.extend([f"- `{path}`" for path in found] or ["- None."])
    lines.extend(["", "### Missing outputs", ""])
    lines.extend([f"- `{path}`" for path in missing] or ["- None."])
    lines.extend(["", "## Key blockers", ""])
    lines.extend([f"- {item}" for item in blockers] or ["- None."])
    lines.extend(["", "## Key warnings", ""])
    lines.extend([f"- {item}" for item in warnings] or ["- None."])
    lines.extend(["", "## Trust failures", ""])
    lines.extend([f"- {item}" for item in trust_failures] or ["- None."])
    lines.extend(
        [
            "",
            "## Detailed checks",
            "",
            checks.to_markdown(index=False),
        ]
    )
    return "\n".join(lines)


def save_github_manual_run_verification(
    output_dir: Path | None = None,
) -> dict[str, object]:
    outputs = output_dir or OUTPUTS_DIR
    checks, summary = build_github_manual_run_verification(outputs)
    outputs.mkdir(parents=True, exist_ok=True)
    csv_path = outputs / VERIFICATION_CSV_FILENAME
    markdown_path = outputs / VERIFICATION_MARKDOWN_FILENAME
    checks.to_csv(csv_path, index=False)
    markdown_path.write_text(
        render_github_manual_run_verification(checks, summary),
        encoding="utf-8",
    )
    return {
        "csv": csv_path,
        "markdown": markdown_path,
        "verdict": summary["verdict"],
        "next_step": summary["next_step"],
    }
