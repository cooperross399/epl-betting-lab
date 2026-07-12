from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, MAX_DEFAULT_JUICE, MIN_EDGE, OUTPUTS_DIR
from epl_betting_lab.data.loaders import load_current_odds, load_matches, load_upcoming_fixtures
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel
from epl_betting_lab.reports.bet_ledger import load_bet_ledger, save_bet_ledger_reports
from epl_betting_lab.reports.bet_ledger_health import save_bet_ledger_health_check
from epl_betting_lab.reports.bet_settlement import build_settlement_preview, save_settlement_preview
from epl_betting_lab.reports.current_odds_validation import (
    CurrentOddsValidationError,
    build_current_odds_validation,
    has_serious_issues,
    render_current_odds_validation_report,
    save_current_odds_validation,
    validation_stop_message,
)
from epl_betting_lab.reports.current_odds_completeness import save_current_odds_completeness
from epl_betting_lab.reports.current_odds_import import process_current_odds_import
from epl_betting_lab.reports.current_odds_template import create_current_odds_template
from epl_betting_lab.reports.current_odds_maintenance import maintain_current_odds
from epl_betting_lab.reports.thursday_best_bets import (
    build_thursday_best_bets,
    list_recent_thursday_archives,
    missing_current_odds_message,
    save_thursday_best_bets,
)
from epl_betting_lab.reports.thursday_best_bets_comparison import save_thursday_best_bets_comparison
from epl_betting_lab.reports.thursday_decision_queue import save_thursday_decision_queue
from epl_betting_lab.reports.tier_performance import save_tier_performance_reports
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.ml_value import evaluate_1x2_value
from epl_betting_lab.strategies.totals import evaluate_total_25


def require_existing_ledger(ledger_path: Path | None = None) -> pd.DataFrame:
    path = ledger_path or MANUAL_DIR / "bet_ledger.csv"
    if not path.exists():
        raise FileNotFoundError(
            "Missing data/manual/bet_ledger.csv. Run `python scripts/run_bet_ledger.py` once from Terminal to create it."
        )
    return load_bet_ledger(path)


def require_existing_current_odds(current_odds_path: Path | None = None) -> Path:
    path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    if not path.exists():
        raise FileNotFoundError(missing_current_odds_message(path))
    return path


def run_bet_ledger_report(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_bet_ledger_reports(require_existing_ledger(ledger_path), output_dir or OUTPUTS_DIR)


def run_ledger_health_check(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_bet_ledger_health_check(require_existing_ledger(ledger_path), output_dir or OUTPUTS_DIR)


def run_settlement_preview(
    ledger_path: Path | None = None,
    matches_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    ledger = require_existing_ledger(ledger_path)
    matches = load_matches(matches_path)
    preview = build_settlement_preview(ledger, matches)
    return save_settlement_preview(preview, output_dir or OUTPUTS_DIR)


def run_current_odds_validation(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_current_odds_validation(current_odds_path or MANUAL_DIR / "current_odds.csv", output_dir or OUTPUTS_DIR)


def run_current_odds_completeness(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    fixtures = load_upcoming_fixtures()
    return save_current_odds_completeness(
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
        fixtures=fixtures,
    )


def _run_refresh_step(
    step_name: str,
    action,
    progress=None,
) -> dict[str, Path]:
    if progress is not None:
        progress(step_name, "running", f"Running {step_name}.")
    try:
        paths = action()
    except Exception as exc:
        if progress is not None:
            progress(step_name, "error", f"{step_name} stopped: {exc}")
        raise
    if progress is not None:
        progress(step_name, "success", f"{step_name} finished.")
    return paths


def run_thursday_readiness_refresh(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    progress=None,
) -> dict[str, dict[str, Path]]:
    """Run safe Thursday reports in order without editing odds or forcing generation."""
    odds_path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    outputs = output_dir or OUTPUTS_DIR
    return {
        "odds_completeness": _run_refresh_step(
            "Odds completeness check",
            lambda: run_current_odds_completeness(odds_path, outputs),
            progress,
        ),
        "current_odds_validation": _run_refresh_step(
            "Current odds validation",
            lambda: run_current_odds_validation(odds_path, outputs),
            progress,
        ),
        "thursday_best_bets": _run_refresh_step(
            "Thursday best-bets generation",
            lambda: run_thursday_best_bets_report(odds_path, outputs, force=False),
            progress,
        ),
    }


def run_create_current_odds_template(
    current_odds_path: Path | None = None,
    book: str = "",
) -> dict[str, Path]:
    fixtures = load_upcoming_fixtures()
    path, _, _ = create_current_odds_template(
        fixtures,
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        overwrite=False,
        book=book,
    )
    return {"csv": path}


def run_current_odds_maintenance_preview(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    book: str = "",
) -> dict[str, Path]:
    fixtures = load_upcoming_fixtures()
    return maintain_current_odds(
        fixtures,
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
        apply=False,
        book=book,
    )


def run_current_odds_import_preview(
    import_path: Path | None = None,
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    *,
    fixtures: pd.DataFrame | None = None,
    matches: pd.DataFrame | None = None,
) -> dict[str, Path]:
    return process_current_odds_import(
        import_path or MANUAL_DIR / "current_odds_import.csv",
        current_odds_path or MANUAL_DIR / "current_odds.csv",
        output_dir or OUTPUTS_DIR,
        apply=False,
        fixtures=fixtures,
        matches=matches,
    )


def run_thursday_best_bets_comparison(output_dir: Path | None = None) -> dict[str, Path]:
    return save_thursday_best_bets_comparison(output_dir or OUTPUTS_DIR)


def run_thursday_decision_queue(output_dir: Path | None = None) -> dict[str, Path]:
    return save_thursday_decision_queue(output_dir or OUTPUTS_DIR)


def run_tier_performance_report(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    return save_tier_performance_reports(ledger_path or MANUAL_DIR / "bet_ledger.csv", output_dir or OUTPUTS_DIR)


def run_post_thursday_review(
    output_dir: Path | None = None,
    progress=None,
) -> dict[str, dict[str, Path]]:
    """Run the read-only post-refresh review reports without editing odds or ledger files."""
    outputs = output_dir or OUTPUTS_DIR
    comparison_paths = _run_refresh_step(
        "Thursday snapshot comparison",
        lambda: run_thursday_best_bets_comparison(outputs),
        progress,
    )
    archives = list_recent_thursday_archives(outputs, limit=2)
    if len(archives) < 2:
        message = (
            "Comparison is not available yet. Generate at least two Thursday best-bets archive snapshots first, "
            "then run post-refresh Thursday review again."
        )
        if progress is not None:
            progress("Thursday decision queue", "error", message)
        raise FileNotFoundError(message)

    decision_queue_paths = _run_refresh_step(
        "Thursday decision queue",
        lambda: run_thursday_decision_queue(outputs),
        progress,
    )
    return {
        "comparison": comparison_paths,
        "decision_queue": decision_queue_paths,
    }


def run_thursday_best_bets_report(
    current_odds_path: Path | None = None,
    output_dir: Path | None = None,
    force: bool = False,
    archive: bool = True,
    overwrite_archive: bool = False,
) -> dict[str, Path]:
    odds_path = current_odds_path or MANUAL_DIR / "current_odds.csv"
    output_dir = output_dir or OUTPUTS_DIR
    if not odds_path.exists():
        validation_issues = build_current_odds_validation(odds_path, matches=pd.DataFrame(), fixtures=pd.DataFrame())
        output_dir.mkdir(parents=True, exist_ok=True)
        validation_issues.to_csv(output_dir / "current_odds_validation.csv", index=False)
        (output_dir / "current_odds_validation.md").write_text(
            render_current_odds_validation_report(validation_issues),
            encoding="utf-8",
        )
        raise CurrentOddsValidationError(validation_stop_message(validation_issues, output_dir))

    matches = load_matches()
    fixtures = load_upcoming_fixtures()
    validation_issues = build_current_odds_validation(odds_path, matches=matches, fixtures=fixtures)
    output_dir.mkdir(parents=True, exist_ok=True)
    validation_issues.to_csv(output_dir / "current_odds_validation.csv", index=False)
    (output_dir / "current_odds_validation.md").write_text(
        render_current_odds_validation_report(validation_issues),
        encoding="utf-8",
    )

    if has_serious_issues(validation_issues) and not force:
        raise CurrentOddsValidationError(validation_stop_message(validation_issues, output_dir))

    odds = load_current_odds(odds_path)

    model = PoissonGoalsModel().fit(matches, last_n_matches_per_team=38)
    projections = model.project_fixtures(fixtures)
    candidates = pd.concat([
        evaluate_1x2_value(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
        evaluate_total_25(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE, matches=matches),
        evaluate_btts(projections, odds, min_edge=MIN_EDGE, max_juice=MAX_DEFAULT_JUICE),
    ], ignore_index=True)

    report = build_thursday_best_bets(candidates)
    return save_thursday_best_bets(
        report,
        output_dir,
        validation_issues=validation_issues,
        forced=force,
        archive=archive,
        overwrite_archive=overwrite_archive,
    )
