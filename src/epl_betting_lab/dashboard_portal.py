from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import MutableMapping

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR
from epl_betting_lab.reports.bet_ledger import load_bet_ledger, summarize_overall


PORTAL_SECTIONS = (
    "Home / Command Center",
    "Thursday Card",
    "Odds Import",
    "Performance Reports",
    "Bet Ledger",
    "Archives & Comparisons",
    "Tools / Diagnostics",
)
PORTAL_SECTION_STATE_KEY = "portal_section"
PORTAL_NAVIGATION_REQUEST_KEY = "portal_navigation_request"

SECTION_DESCRIPTIONS = {
    "Home / Command Center": "Start here for Thursday readiness and the next manual step.",
    "Thursday Card": "Validate prices, review incomplete odds, and read the latest card.",
    "Odds Import": "Move a sportsbook export through the safe preview workflow.",
    "Performance Reports": "Review backtests, confidence tiers, CLV, and profit breakdowns.",
    "Bet Ledger": "Track record, pending bets, health checks, and settlement previews.",
    "Archives & Comparisons": "Compare saved Thursday cards and review the decision queue.",
    "Tools / Diagnostics": "Open model projections, workflow files, and advanced diagnostics.",
}


def resolve_open_next_section(cue: object) -> str | None:
    normalized = " ".join(str(cue or "").strip().lower().split())
    if not normalized:
        return None

    mappings = (
        (
            (
                "decision queue",
                "snapshot comparison",
                "archive comparison",
                "recent thursday report archives",
                "archive history",
                "archives & comparisons",
            ),
            "Archives & Comparisons",
        ),
        (
            (
                "odds import",
                "export profile",
                "profile install",
                "installed profile",
                "rollback preview",
                "export conversion",
            ),
            "Odds Import",
        ),
        (
            ("tier performance", "performance reports", "backtest", "clv"),
            "Performance Reports",
        ),
        (
            ("bet ledger", "ledger health", "settlement", "pending bets"),
            "Bet Ledger",
        ),
        (
            ("tools / diagnostics", "model projections", "workflow checklist", "diagnostics"),
            "Tools / Diagnostics",
        ),
        (
            (
                "thursday card",
                "thursday readiness",
                "best-bets report",
                "current odds validation",
                "odds entry completeness",
            ),
            "Thursday Card",
        ),
    )
    for phrases, section in mappings:
        if any(phrase in normalized for phrase in phrases):
            return section
    return None


def apply_portal_navigation_request(state: MutableMapping[str, object]) -> str:
    current = state.get(PORTAL_SECTION_STATE_KEY)
    if current not in PORTAL_SECTIONS:
        current = PORTAL_SECTIONS[0]

    requested = state.pop(PORTAL_NAVIGATION_REQUEST_KEY, None)
    if requested in PORTAL_SECTIONS:
        current = requested

    state[PORTAL_SECTION_STATE_KEY] = current
    return str(current)


@dataclass(frozen=True)
class OddsImportStep:
    number: int
    label: str
    description: str


ODDS_IMPORT_STEPS = (
    OddsImportStep(1, "Diagnose export", "Find the closest installed column-mapping profile."),
    OddsImportStep(2, "Suggest profile", "Create a review-only draft when no profile fits."),
    OddsImportStep(3, "Validate suggested profile", "Test the draft mapping entirely in memory."),
    OddsImportStep(4, "Preview profile install", "Review the exact registry change before Terminal apply."),
    OddsImportStep(5, "Verify installed profile", "Check an installed profile against the source export."),
    OddsImportStep(6, "Rollback preview", "Compare a registry backup without restoring it."),
    OddsImportStep(7, "Convert export", "Preview standardized odds rows without creating an import file."),
    OddsImportStep(8, "Preview current odds import", "Validate additions and updates without applying them."),
    OddsImportStep(9, "View import audits", "Review prior Terminal apply batches and backups."),
)


@dataclass(frozen=True)
class LedgerPortalSummary:
    status: str
    record: str
    profit_units: float | None
    roi: float | None
    pending_bets: int | None
    message: str


def build_ledger_portal_summary(
    ledger_path: Path | None = None,
) -> LedgerPortalSummary:
    ledger_path = ledger_path or MANUAL_DIR / "bet_ledger.csv"
    if not ledger_path.exists():
        return LedgerPortalSummary(
            status="Missing",
            record="Missing",
            profit_units=None,
            roi=None,
            pending_bets=None,
            message="Create the manual ledger before ledger metrics can be shown.",
        )

    try:
        overall = summarize_overall(load_bet_ledger(ledger_path))
    except (
        OSError,
        UnicodeError,
        ValueError,
        pd.errors.EmptyDataError,
        pd.errors.ParserError,
    ) as exc:
        return LedgerPortalSummary(
            status="Needs review",
            record="Unavailable",
            profit_units=None,
            roi=None,
            pending_bets=None,
            message=f"The ledger could not be summarized: {exc}",
        )

    record = f"{overall['wins']}-{overall['losses']}-{overall['pushes']}"
    return LedgerPortalSummary(
        status="Ready",
        record=record,
        profit_units=float(overall["profit_units"]),
        roi=float(overall["roi"]),
        pending_bets=int(overall["pending_bets"]),
        message="Ledger figures include settled bets; pending bets stay out of ROI.",
    )
