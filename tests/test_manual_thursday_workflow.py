from __future__ import annotations

import re
from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "manual-thursday-workflow.yml"
)


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_manual_thursday_workflow_has_no_schedule_or_cron() -> None:
    text = _workflow_text()

    assert re.search(r"(?m)^on:\n  workflow_dispatch:\s*$", text)
    assert not re.search(r"(?m)^\s+schedule:\s*$", text)
    assert not re.search(r"(?m)^\s+-?\s*cron:", text)


def test_manual_thursday_workflow_runs_supported_checks_and_runner() -> None:
    text = _workflow_text()

    assert "uses: actions/checkout@v4" in text
    assert "uses: actions/setup-python@v5" in text
    assert 'python-version: "3.11"' in text
    assert "python -m pip install -r requirements.txt" in text
    assert "python -m compileall -q src scripts app.py" in text
    assert "python -m pytest" in text
    assert "python scripts/run_scheduled_thursday_workflow.py" in text
    assert "python scripts/verify_github_manual_thursday_run.py" in text
    assert "id: verification" in text
    assert "--github-runner-handoff" in text
    assert '--current-odds-path="$CURRENT_ODDS_PATH"' in text
    assert '--fixtures-path="$FIXTURES_PATH"' in text
    assert '--staging-receipt-path="$STAGING_RECEIPT_PATH"' in text
    assert "--require-staging-receipt" in text
    assert "--force" not in text


def test_manual_thursday_workflow_accepts_only_prepared_repository_input_paths() -> None:
    text = _workflow_text()

    assert "current_odds_path:" in text
    assert "default: data/staging/current_odds_staging.csv" in text
    assert "fixtures_path:" in text
    assert "default: data/staging/upcoming_fixtures_staging.csv" in text
    assert "staging_receipt_path:" in text
    assert "default: data/outputs/staging_input_validation.json" in text
    assert "expected_current_odds_sha256:" in text
    assert "expected_fixtures_sha256:" in text
    assert "persist-credentials: false" in text


def test_manual_thursday_workflow_always_uploads_reports_and_writes_summary() -> None:
    text = _workflow_text()

    assert "uses: actions/upload-artifact@v4" in text
    assert "path: data/outputs/" in text
    assert "if: always()" in text
    assert "scheduled_thursday_workflow_summary.json" in text
    assert "$GITHUB_STEP_SUMMARY" in text
    assert "Download it from the **Artifacts** section" in text
    assert "### Input handoff proof" in text
    assert "Staging receipt verdict:" in text
    assert "Staging receipt generated at:" in text
    assert "Staging receipt binding:" in text
    assert "Receipt input checksums:" in text
    assert "Odds file used:" in text
    assert "Odds SHA-256:" in text
    assert "Fixtures freshness:" in text
    assert "Odds completeness:" in text
    assert "Card generation allowed:" in text
    assert "github_manual_thursday_run_verification.csv" in text
    assert "### Manual run verification" in text


def test_manual_thursday_workflow_allows_blocked_but_fails_runtime_errors() -> None:
    text = _workflow_text()

    assert "continue-on-error: true" in text
    assert 'if [[ "${exit_code}" -eq 2 ]]' in text
    assert 'case "${RUNNER_EXIT_CODE}" in' in text
    assert re.search(
        r'(?s)\n\s+2\)\n.*Action remains successful.*\n\s+;;',
        text,
    )
    assert re.search(
        r'(?s)\n\s+1\)\n.*runtime failure.*\n\s+exit 1',
        text,
    )
    assert "VERIFICATION_OUTCOME: ${{ steps.verification.outcome }}" in text
    assert "Manual Thursday run verification did not produce" in text


def test_manual_thursday_workflow_contains_no_apply_actions() -> None:
    text = _workflow_text()
    forbidden = (
        "--apply",
        "archive_stale_current_odds.py",
        "rollback_stale_current_odds_archive.py",
        "import_current_odds.py",
        "settle_bet_ledger.py",
        "preview_install_odds_profile.py",
    )

    assert all(command not in text for command in forbidden)
