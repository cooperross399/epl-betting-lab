from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd

from epl_betting_lab.reports.bet_ledger import LEDGER_COLUMNS, empty_ledger, load_bet_ledger


DEFAULT_PREFILL_STATUSES = ["BETTABLE", "LEAN"]


def _blank_if_missing(row: pd.Series, column: str) -> object:
    if column not in row or pd.isna(row[column]):
        return pd.NA
    return row[column]


def _status_allowed(status: object, allowed_statuses: list[str]) -> bool:
    if pd.isna(status):
        return False
    cleaned = str(status).strip().upper()
    return any(cleaned == allowed.upper() or cleaned.startswith(f"{allowed.upper()} ") for allowed in allowed_statuses)


def _slug(value: object) -> str:
    if pd.isna(value) or str(value).strip() == "":
        return "blank"
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "blank"


def _stable_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def stable_bet_id(row: pd.Series) -> str:
    parts = [
        _blank_if_missing(row, "date"),
        _blank_if_missing(row, "season"),
        _blank_if_missing(row, "home_team"),
        _blank_if_missing(row, "away_team"),
        _blank_if_missing(row, "market"),
        _blank_if_missing(row, "selection"),
        _blank_if_missing(row, "american_odds"),
    ]
    seed = "|".join(_stable_value(part) for part in parts)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    prefix = "-".join([
        _slug(_blank_if_missing(row, "date")),
        _slug(_blank_if_missing(row, "home_team")),
        _slug(_blank_if_missing(row, "away_team")),
        _slug(_blank_if_missing(row, "market")),
        _slug(_blank_if_missing(row, "selection")),
    ])
    return f"{prefix}-{digest}"


def load_weekly_card(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Weekly card not found at {path}. Run `python scripts/generate_weekly_card.py` first."
        )
    return pd.read_csv(path)


def weekly_card_to_ledger_rows(
    weekly_card: pd.DataFrame,
    allowed_statuses: list[str] | None = None,
) -> pd.DataFrame:
    allowed = allowed_statuses or DEFAULT_PREFILL_STATUSES
    if weekly_card.empty:
        return empty_ledger()

    rows = []
    for _, card_row in weekly_card.iterrows():
        status = _blank_if_missing(card_row, "status")
        if not _status_allowed(status, allowed):
            continue

        match = _blank_if_missing(card_row, "match")
        if pd.isna(match):
            home = _blank_if_missing(card_row, "home_team")
            away = _blank_if_missing(card_row, "away_team")
            match = f"{home} vs {away}" if pd.notna(home) and pd.notna(away) else pd.NA

        ledger_row = {
            "bet_id": stable_bet_id(card_row),
            "date": _blank_if_missing(card_row, "date"),
            "season": _blank_if_missing(card_row, "season"),
            "match": match,
            "home_team": _blank_if_missing(card_row, "home_team"),
            "away_team": _blank_if_missing(card_row, "away_team"),
            "market": _blank_if_missing(card_row, "market"),
            "selection": _blank_if_missing(card_row, "selection"),
            "model_recommendation_status": status,
            "raw_model_prob": _blank_if_missing(card_row, "raw_model_prob"),
            "calibrated_model_prob": _blank_if_missing(card_row, "calibrated_model_prob"),
            "raw_edge": _blank_if_missing(card_row, "raw_edge"),
            "calibrated_edge": _blank_if_missing(card_row, "calibrated_edge"),
            "american_odds": _blank_if_missing(card_row, "american_odds"),
            "closing_american_odds": pd.NA,
            "stake_units": _blank_if_missing(card_row, "suggested_units"),
            "stake_dollars": _blank_if_missing(card_row, "suggested_wager_$"),
            "result": "pending",
            "profit_units": pd.NA,
            "profit_dollars": pd.NA,
            "clv_probability_points": pd.NA,
            "book": _blank_if_missing(card_row, "book"),
            "notes": "draft from weekly card",
        }

        if pd.isna(ledger_row["raw_model_prob"]):
            ledger_row["raw_model_prob"] = _blank_if_missing(card_row, "model_prob")
        if pd.isna(ledger_row["calibrated_model_prob"]):
            ledger_row["calibrated_model_prob"] = _blank_if_missing(card_row, "model_prob")
        if pd.isna(ledger_row["raw_edge"]):
            ledger_row["raw_edge"] = _blank_if_missing(card_row, "edge")
        if pd.isna(ledger_row["calibrated_edge"]):
            ledger_row["calibrated_edge"] = _blank_if_missing(card_row, "edge")

        rows.append(ledger_row)

    return pd.DataFrame(rows, columns=LEDGER_COLUMNS) if rows else empty_ledger()


def merge_draft_rows(
    existing_ledger: pd.DataFrame,
    draft_rows: pd.DataFrame,
    overwrite_existing: bool = False,
) -> tuple[pd.DataFrame, dict[str, int]]:
    existing = existing_ledger.copy() if not existing_ledger.empty else empty_ledger()
    drafts = draft_rows.copy() if not draft_rows.empty else empty_ledger()
    for column in LEDGER_COLUMNS:
        if column not in existing.columns:
            existing[column] = pd.NA
        if column not in drafts.columns:
            drafts[column] = pd.NA
    existing = existing[LEDGER_COLUMNS]
    drafts = drafts[LEDGER_COLUMNS]

    if drafts.empty:
        return existing, {"draft_rows": 0, "added_rows": 0, "skipped_duplicates": 0, "overwritten_rows": 0}

    existing_ids = set(existing["bet_id"].dropna().astype(str))
    duplicate_mask = drafts["bet_id"].astype(str).isin(existing_ids)
    duplicates = int(duplicate_mask.sum())

    if overwrite_existing and duplicates:
        replace_ids = set(drafts.loc[duplicate_mask, "bet_id"].astype(str))
        kept_existing = existing[~existing["bet_id"].astype(str).isin(replace_ids)]
        merged = pd.concat([kept_existing, drafts], ignore_index=True)
        return merged[LEDGER_COLUMNS], {
            "draft_rows": int(len(drafts)),
            "added_rows": int(len(drafts) - duplicates),
            "skipped_duplicates": 0,
            "overwritten_rows": duplicates,
        }

    new_rows = drafts[~duplicate_mask]
    merged = pd.concat([existing, new_rows], ignore_index=True)
    return merged[LEDGER_COLUMNS], {
        "draft_rows": int(len(drafts)),
        "added_rows": int(len(new_rows)),
        "skipped_duplicates": duplicates,
        "overwritten_rows": 0,
    }


def prefill_ledger_from_weekly_card(
    weekly_card_path: Path,
    ledger_path: Path,
    allowed_statuses: list[str] | None = None,
    overwrite_existing: bool = False,
) -> dict[str, int]:
    weekly_card = load_weekly_card(weekly_card_path)
    existing = load_bet_ledger(ledger_path)
    draft_rows = weekly_card_to_ledger_rows(weekly_card, allowed_statuses)
    merged, stats = merge_draft_rows(existing, draft_rows, overwrite_existing=overwrite_existing)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(ledger_path, index=False)
    return stats
