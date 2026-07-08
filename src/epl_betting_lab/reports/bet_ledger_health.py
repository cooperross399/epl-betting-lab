from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.bet_ledger import LEDGER_COLUMNS


HEALTH_COLUMNS = [
    "severity",
    "issue",
    "bet_id",
    "row_number",
    "match",
    "market",
    "selection",
    "result",
    "details",
]

VALID_RESULTS = {"win", "loss", "push", "pending"}
VALID_SELECTIONS = {
    "1x2": {"home", "draw", "away"},
    "total_2_5": {"over", "under"},
    "btts": {"yes", "no"},
}
SERIOUS_SEVERITIES = {"error", "warning"}


def _is_blank(value: object) -> bool:
    return pd.isna(value) or str(value).strip() == ""


def _clean(value: object) -> str:
    return "" if _is_blank(value) else str(value).strip().lower()


def _add_issue(
    rows: list[dict[str, object]],
    severity: str,
    issue: str,
    row: pd.Series | None = None,
    row_number: int | None = None,
    details: str = "",
) -> None:
    rows.append({
        "severity": severity,
        "issue": issue,
        "bet_id": row.get("bet_id", pd.NA) if row is not None else pd.NA,
        "row_number": row_number if row_number is not None else pd.NA,
        "match": row.get("match", pd.NA) if row is not None else pd.NA,
        "market": row.get("market", pd.NA) if row is not None else pd.NA,
        "selection": row.get("selection", pd.NA) if row is not None else pd.NA,
        "result": row.get("result", pd.NA) if row is not None else pd.NA,
        "details": details,
    })


def build_bet_ledger_health_check(ledger: pd.DataFrame) -> pd.DataFrame:
    """Return ledger quality issues without changing ledger data."""
    if ledger.empty:
        return pd.DataFrame(columns=HEALTH_COLUMNS)

    df = ledger.copy()
    for column in LEDGER_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    issues: list[dict[str, object]] = []
    duplicate_ids = df["bet_id"][df["bet_id"].notna() & df["bet_id"].astype(str).str.strip().ne("")]
    duplicate_ids = set(duplicate_ids[duplicate_ids.duplicated(keep=False)].astype(str))

    for index, row in df.iterrows():
        row_number = int(index) + 2
        bet_id = row.get("bet_id")
        market = _clean(row.get("market"))
        selection = _clean(row.get("selection"))
        result = _clean(row.get("result"))
        is_pending = result in {"", "pending"}
        is_settled = result in {"win", "loss", "push"}

        if not _is_blank(bet_id) and str(bet_id).strip() in duplicate_ids:
            _add_issue(
                issues,
                "error",
                "duplicate_bet_id",
                row,
                row_number,
                "Duplicate bet_id values can double count or overwrite tracking rows.",
            )
        if _is_blank(row.get("american_odds")):
            _add_issue(issues, "error", "missing_american_odds", row, row_number, "American odds are needed for profit and CLV math.")
        if is_settled and _is_blank(row.get("stake_units")):
            _add_issue(issues, "error", "missing_settled_stake_units", row, row_number, "Settled bets need stake_units for accurate unit ROI.")
        if is_pending and _is_blank(row.get("stake_units")):
            _add_issue(issues, "warning", "missing_pending_stake_units", row, row_number, "Confirm stake_units before this pending bet is settled.")
        if result == "":
            _add_issue(issues, "error", "missing_result", row, row_number, "Use win, loss, push, or pending.")
        elif result not in VALID_RESULTS:
            _add_issue(issues, "error", "invalid_result", row, row_number, "Valid results are win, loss, push, and pending.")
        if is_settled and _is_blank(row.get("profit_units")):
            _add_issue(
                issues,
                "warning",
                "settled_profit_blank",
                row,
                row_number,
                "Profit can be auto-calculated by reports, but fill it manually if you require a locked ledger value.",
            )
        if _is_blank(row.get("closing_american_odds")):
            _add_issue(
                issues,
                "info",
                "missing_closing_american_odds",
                row,
                row_number,
                "Optional missing CLV: add the closing line later if you want CLV tracking.",
            )
        if market not in VALID_SELECTIONS:
            _add_issue(issues, "error", "invalid_market", row, row_number, "Supported markets are 1x2, total_2_5, and btts.")
        elif selection not in VALID_SELECTIONS[market]:
            allowed = ", ".join(sorted(VALID_SELECTIONS[market]))
            _add_issue(issues, "error", "invalid_selection", row, row_number, f"Supported selections for {market}: {allowed}.")
        if _is_blank(row.get("home_team")) or _is_blank(row.get("away_team")):
            _add_issue(issues, "error", "missing_team", row, row_number, "Both home_team and away_team are needed for matching and summaries.")
        if is_pending and _clean(row.get("notes")) == "draft from weekly card":
            _add_issue(
                issues,
                "warning",
                "draft_recommendation_not_confirmed",
                row,
                row_number,
                "This row looks like a prefilled model recommendation. Confirm it was actually placed or delete it.",
            )

    return pd.DataFrame(issues, columns=HEALTH_COLUMNS)


def render_health_check_report(issues: pd.DataFrame) -> str:
    if issues.empty:
        quick = "No ledger issues found."
        serious = optional = pd.DataFrame(columns=HEALTH_COLUMNS)
    else:
        serious = issues[issues["severity"].isin(SERIOUS_SEVERITIES)]
        optional = issues[~issues["severity"].isin(SERIOUS_SEVERITIES)]
        quick = (
            f"{len(serious)} serious issues and {len(optional)} optional cleanup items found."
        )

    lines = [
        "# EPL Betting Lab Ledger Health Check",
        "",
        "This report checks manual ledger quality. It does not change the model, fetch odds, place bets, or edit the ledger.",
        "",
        "## Quick summary",
        "",
        f"- {quick}",
        "- Serious issues can affect profit/loss, settlement, matching, or summaries.",
        "- Optional items, like missing closing odds, are useful for CLV but should not block normal tracking.",
        "",
        "## Serious issues",
        "",
        serious.to_markdown(index=False) if not serious.empty else "No serious issues found.",
        "",
        "## Optional cleanup",
        "",
        optional.to_markdown(index=False) if not optional.empty else "No optional cleanup items found.",
    ]
    return "\n".join(lines)


def save_bet_ledger_health_check(ledger: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    issues = build_bet_ledger_health_check(ledger)
    csv_path = output_dir / "bet_ledger_health_check.csv"
    markdown_path = output_dir / "bet_ledger_health_check.md"
    issues.to_csv(csv_path, index=False)
    markdown_path.write_text(render_health_check_report(issues), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}
