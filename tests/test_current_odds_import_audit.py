from __future__ import annotations

import pandas as pd

from epl_betting_lab.reports.current_odds_import_audit import (
    AUDIT_COLUMNS,
    load_current_odds_import_audit,
    save_current_odds_import_audit,
    summarize_current_odds_import_batches,
)


def test_audit_loader_has_beginner_friendly_missing_and_unreadable_fallbacks(tmp_path) -> None:
    path = tmp_path / "current_odds_import_audit.csv"

    missing, missing_message = load_current_odds_import_audit(path)
    assert missing is not None and missing.empty
    assert "No current odds import audit history yet" in missing_message

    path.write_text('batch_id,applied_at\n"broken', encoding="utf-8")
    unreadable, unreadable_message = load_current_odds_import_audit(path)
    assert unreadable is None
    assert "unreadable" in unreadable_message

    pd.DataFrame([{"batch_id": "batch-1"}]).to_csv(path, index=False)
    malformed, malformed_message = load_current_odds_import_audit(path)
    assert malformed is None
    assert "missing required columns" in malformed_message


def test_batch_summary_labels_missing_backup_path() -> None:
    row = {column: "" for column in AUDIT_COLUMNS}
    row.update({
        "batch_id": "batch-1",
        "applied_at": "2026-07-12T12:00:00-04:00",
        "batch_status": "applied",
        "rows_added": "1",
    })

    summary = summarize_current_odds_import_batches(pd.DataFrame([row], columns=AUDIT_COLUMNS))

    assert summary.iloc[0]["backup_path"] == "Not available (new file or no valid changes)"


def test_unreadable_cumulative_audit_is_not_overwritten(tmp_path) -> None:
    audit_path = tmp_path / "current_odds_import_audit.csv"
    original = 'batch_id,applied_at\n"broken'
    audit_path.write_text(original, encoding="utf-8")
    row = {column: "" for column in AUDIT_COLUMNS}
    row.update({
        "batch_id": "batch-safe",
        "applied_at": "2026-07-12T12:00:00-04:00",
        "batch_status": "no_changes",
        "row_action": "no_rows",
        "before_values": "{}",
        "after_values": "{}",
    })

    paths = save_current_odds_import_audit(pd.DataFrame([row], columns=AUDIT_COLUMNS), tmp_path)

    assert audit_path.read_text(encoding="utf-8") == original
    assert paths["batch_audit_csv"].exists()
    report = paths["audit_markdown"].read_text(encoding="utf-8")
    assert "cumulative CSV was left untouched" in report
    assert str(paths["batch_audit_csv"]) in report
