from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR


@dataclass(frozen=True)
class CurrentOddsStatus:
    status: str
    explanation: str
    command: str
    validation_csv: Path
    validation_markdown: Path
    current_odds: Path
    serious_issues: int = 0
    warnings: int = 0
    is_stale: bool = False


VALIDATE_COMMAND = "python scripts/validate_current_odds.py"


def _is_stale(validation_csv: Path, validation_markdown: Path, current_odds: Path) -> bool:
    if not current_odds.exists():
        return False
    newest_validation = max(
        (path.stat().st_mtime for path in [validation_csv, validation_markdown] if path.exists()),
        default=None,
    )
    return newest_validation is not None and current_odds.stat().st_mtime > newest_validation


def build_current_odds_status(
    validation_csv: Path | None = None,
    validation_markdown: Path | None = None,
    current_odds: Path | None = None,
) -> CurrentOddsStatus:
    validation_csv = validation_csv or OUTPUTS_DIR / "current_odds_validation.csv"
    validation_markdown = validation_markdown or OUTPUTS_DIR / "current_odds_validation.md"
    current_odds = current_odds or MANUAL_DIR / "current_odds.csv"

    if not validation_csv.exists() and not validation_markdown.exists():
        return CurrentOddsStatus(
            status="Not checked",
            explanation="Run validation before generating Thursday best bets.",
            command=VALIDATE_COMMAND,
            validation_csv=validation_csv,
            validation_markdown=validation_markdown,
            current_odds=current_odds,
        )

    stale = _is_stale(validation_csv, validation_markdown, current_odds)
    if stale:
        return CurrentOddsStatus(
            status="Needs refresh",
            explanation="current_odds.csv changed after the latest validation report.",
            command=VALIDATE_COMMAND,
            validation_csv=validation_csv,
            validation_markdown=validation_markdown,
            current_odds=current_odds,
            is_stale=True,
        )

    if not validation_csv.exists():
        return CurrentOddsStatus(
            status="Not checked",
            explanation="The markdown report exists, but the CSV issue list is missing. Regenerate validation.",
            command=VALIDATE_COMMAND,
            validation_csv=validation_csv,
            validation_markdown=validation_markdown,
            current_odds=current_odds,
        )

    issues = pd.read_csv(validation_csv)
    if issues.empty or "severity" not in issues.columns:
        return CurrentOddsStatus(
            status="Ready",
            explanation="No serious issues or warnings were found in the latest validation.",
            command=VALIDATE_COMMAND,
            validation_csv=validation_csv,
            validation_markdown=validation_markdown,
            current_odds=current_odds,
        )

    severities = issues["severity"].fillna("").astype(str).str.lower()
    serious = int((severities == "error").sum())
    warnings = int((severities == "warning").sum())

    if serious > 0:
        return CurrentOddsStatus(
            status="Blocked",
            explanation=f"{serious} serious issue(s) must be fixed before the dashboard generates Thursday best bets.",
            command=VALIDATE_COMMAND,
            validation_csv=validation_csv,
            validation_markdown=validation_markdown,
            current_odds=current_odds,
            serious_issues=serious,
            warnings=warnings,
        )
    if warnings > 0:
        return CurrentOddsStatus(
            status="Warnings only",
            explanation=f"{warnings} warning(s) need review, but there are no serious blockers.",
            command=VALIDATE_COMMAND,
            validation_csv=validation_csv,
            validation_markdown=validation_markdown,
            current_odds=current_odds,
            warnings=warnings,
        )
    return CurrentOddsStatus(
        status="Ready",
        explanation="No serious issues or warnings were found in the latest validation.",
        command=VALIDATE_COMMAND,
        validation_csv=validation_csv,
        validation_markdown=validation_markdown,
        current_odds=current_odds,
    )
