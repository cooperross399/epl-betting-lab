from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR


READINESS_COMMAND = "python scripts/check_current_odds_completeness.py && python scripts/validate_current_odds.py"


@dataclass(frozen=True)
class ThursdayReadiness:
    odds_completion_percentage: float | None
    incomplete_matches: int | None
    serious_validation_issues: int | None
    validation_warnings: int | None
    thursday_report_status: str
    explanation: str
    command: str
    is_stale: bool = False
    completeness_missing: bool = False
    validation_missing: bool = False
    thursday_report_missing: bool = False


def _is_stale(report_paths: tuple[Path, ...], current_odds: Path) -> bool:
    if not current_odds.exists():
        return False
    existing = [path for path in report_paths if path.exists()]
    if not existing:
        return False
    newest_report = max(path.stat().st_mtime for path in existing)
    return current_odds.stat().st_mtime > newest_report


def _read_markdown_metric(markdown: Path, label: str) -> str | None:
    if not markdown.exists():
        return None
    pattern = rf"^- {re.escape(label)}:\s*(.+)$"
    for line in markdown.read_text(encoding="utf-8").splitlines():
        match = re.match(pattern, line.strip())
        if match:
            return match.group(1).strip()
    return None


def _read_completion_percentage(markdown: Path) -> float | None:
    value = _read_markdown_metric(markdown, "Completion percentage")
    if value is None:
        return None
    cleaned = value.replace("%", "").strip()
    try:
        return float(cleaned) / 100
    except ValueError:
        return None


def _read_int_metric(markdown: Path, label: str) -> int | None:
    value = _read_markdown_metric(markdown, label)
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _validation_counts(validation_csv: Path) -> tuple[int | None, int | None]:
    if not validation_csv.exists():
        return None, None
    issues = pd.read_csv(validation_csv)
    if issues.empty or "severity" not in issues.columns:
        return 0, 0
    severities = issues["severity"].fillna("").astype(str).str.lower()
    return int((severities == "error").sum()), int((severities == "warning").sum())


def build_thursday_readiness(
    output_dir: Path | None = None,
    current_odds: Path | None = None,
) -> ThursdayReadiness:
    output_dir = output_dir or OUTPUTS_DIR
    current_odds = current_odds or MANUAL_DIR / "current_odds.csv"
    completeness_csv = output_dir / "current_odds_completeness.csv"
    completeness_md = output_dir / "current_odds_completeness.md"
    validation_csv = output_dir / "current_odds_validation.csv"
    validation_md = output_dir / "current_odds_validation.md"
    thursday_csv = output_dir / "thursday_best_bets.csv"
    thursday_md = output_dir / "thursday_best_bets.md"

    completeness_missing = not completeness_csv.exists() and not completeness_md.exists()
    validation_missing = not validation_csv.exists() and not validation_md.exists()
    thursday_report_missing = not thursday_csv.exists() and not thursday_md.exists()

    completion = _read_completion_percentage(completeness_md)
    incomplete_matches = _read_int_metric(completeness_md, "Matches incomplete")
    serious, warnings = _validation_counts(validation_csv)

    report_paths = (
        completeness_csv,
        completeness_md,
        validation_csv,
        validation_md,
        thursday_csv,
        thursday_md,
    )
    stale = _is_stale(report_paths, current_odds)
    if stale:
        return ThursdayReadiness(
            odds_completion_percentage=completion,
            incomplete_matches=incomplete_matches,
            serious_validation_issues=serious,
            validation_warnings=warnings,
            thursday_report_status="Needs refresh",
            explanation="current_odds.csv changed after one or more Thursday workflow reports.",
            command=READINESS_COMMAND,
            is_stale=True,
            completeness_missing=completeness_missing,
            validation_missing=validation_missing,
            thursday_report_missing=thursday_report_missing,
        )

    if completeness_missing or validation_missing:
        missing = []
        if completeness_missing:
            missing.append("odds completeness")
        if validation_missing:
            missing.append("current odds validation")
        return ThursdayReadiness(
            odds_completion_percentage=completion,
            incomplete_matches=incomplete_matches,
            serious_validation_issues=serious,
            validation_warnings=warnings,
            thursday_report_status="Not checked",
            explanation=f"Missing {', '.join(missing)} report(s). Run the safe report buttons before generating Thursday best bets.",
            command=READINESS_COMMAND,
            completeness_missing=completeness_missing,
            validation_missing=validation_missing,
            thursday_report_missing=thursday_report_missing,
        )

    serious = serious or 0
    warnings = warnings or 0
    if serious > 0:
        status = "Blocked"
        explanation = f"{serious} serious current-odds validation issue(s) must be fixed."
    elif warnings > 0:
        status = "Warnings only"
        explanation = f"{warnings} current-odds warning(s) need review."
    else:
        status = "Ready"
        explanation = "Completeness and validation reports have no serious blockers."

    if thursday_report_missing:
        explanation = f"{explanation} Thursday best-bets report has not been generated yet."

    return ThursdayReadiness(
        odds_completion_percentage=completion,
        incomplete_matches=incomplete_matches,
        serious_validation_issues=serious,
        validation_warnings=warnings,
        thursday_report_status=status,
        explanation=explanation,
        command=READINESS_COMMAND,
        completeness_missing=completeness_missing,
        validation_missing=validation_missing,
        thursday_report_missing=thursday_report_missing,
    )
