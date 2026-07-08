from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import BANKROLL_UNIT_DOLLARS
from epl_betting_lab.reports.bet_ledger import LEDGER_COLUMNS, enrich_bet_ledger, empty_ledger


PREVIEW_COLUMNS = [
    "bet_id",
    "match",
    "market",
    "selection",
    "current_result_status",
    "suggested_result",
    "final_score",
    "reason",
]


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def _same_value(left: object, right: object) -> bool:
    if pd.isna(left) or pd.isna(right):
        return False
    return str(left).strip() == str(right).strip()


def _pending_rows(ledger: pd.DataFrame) -> pd.DataFrame:
    if ledger.empty:
        return empty_ledger()
    df = ledger.copy()
    for column in LEDGER_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    result = df["result"].fillna("pending").astype(str).str.strip().str.lower()
    return df[result.eq("pending")].copy()


def _finished_matches(matches: pd.DataFrame) -> pd.DataFrame:
    if matches.empty:
        return matches.copy()
    required = {"home_team", "away_team", "home_goals", "away_goals"}
    missing = required - set(matches.columns)
    if missing:
        raise ValueError(f"Finished match data is missing required columns: {sorted(missing)}")
    return matches[matches["home_goals"].notna() & matches["away_goals"].notna()].copy()


def _match_for_bet(bet: pd.Series, matches: pd.DataFrame) -> tuple[pd.Series | None, str]:
    home = _clean_text(bet.get("home_team"))
    away = _clean_text(bet.get("away_team"))
    if not home or not away:
        return None, "Missing home_team or away_team on the ledger row."

    candidates = matches[
        matches["home_team"].apply(_clean_text).eq(home)
        & matches["away_team"].apply(_clean_text).eq(away)
    ].copy()

    if "season" in candidates.columns and pd.notna(bet.get("season")):
        season_matches = candidates[candidates["season"].apply(lambda value: _same_value(value, bet.get("season")))]
        if not season_matches.empty:
            candidates = season_matches

    if "date" in candidates.columns and pd.notna(bet.get("date")):
        ledger_date = pd.to_datetime(bet.get("date"), errors="coerce")
        if pd.notna(ledger_date):
            match_dates = pd.to_datetime(candidates["date"], errors="coerce")
            date_matches = candidates[match_dates.dt.date == ledger_date.date()]
            if not date_matches.empty:
                candidates = date_matches

    if len(candidates) == 1:
        return candidates.iloc[0], "Matched by home team, away team, season/date when available."
    if len(candidates) == 0:
        return None, "No finished match found for this home/away pairing."
    return None, "Multiple possible matches found; not confident enough to settle automatically."


def settle_market(market: object, selection: object, home_goals: int, away_goals: int) -> tuple[str, str]:
    market_text = _clean_text(market)
    selection_text = _clean_text(selection)
    total_goals = home_goals + away_goals

    if market_text == "1x2":
        if home_goals > away_goals:
            winner = "home"
        elif away_goals > home_goals:
            winner = "away"
        else:
            winner = "draw"
        if selection_text in {"home", "draw", "away"}:
            return ("win" if selection_text == winner else "loss", f"1X2 result was {winner}.")
        return "unmatched", f"Unsupported 1X2 selection '{selection}'."

    if market_text == "total_2_5":
        if selection_text == "over":
            return ("win" if total_goals > 2.5 else "loss", f"Final total was {total_goals} goals.")
        if selection_text == "under":
            return ("win" if total_goals < 2.5 else "loss", f"Final total was {total_goals} goals.")
        return "unmatched", f"Unsupported total_2_5 selection '{selection}'."

    if market_text == "btts":
        btts_yes = home_goals > 0 and away_goals > 0
        if selection_text == "yes":
            return ("win" if btts_yes else "loss", f"BTTS was {'yes' if btts_yes else 'no'}.")
        if selection_text == "no":
            return ("win" if not btts_yes else "loss", f"BTTS was {'yes' if btts_yes else 'no'}.")
        return "unmatched", f"Unsupported BTTS selection '{selection}'."

    return "unmatched", f"Unsupported market '{market}'."


def build_settlement_preview(ledger: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    pending = _pending_rows(ledger)
    finished = _finished_matches(matches)
    if pending.empty:
        return pd.DataFrame(columns=PREVIEW_COLUMNS)

    rows = []
    for _, bet in pending.iterrows():
        match, match_reason = _match_for_bet(bet, finished)
        suggested = "unmatched"
        final_score = pd.NA
        reason = match_reason
        if match is not None:
            home_goals = int(match["home_goals"])
            away_goals = int(match["away_goals"])
            final_score = f"{home_goals}-{away_goals}"
            suggested, market_reason = settle_market(bet.get("market"), bet.get("selection"), home_goals, away_goals)
            reason = f"{match_reason} {market_reason}"

        rows.append({
            "bet_id": bet.get("bet_id", pd.NA),
            "match": bet.get("match", pd.NA),
            "market": bet.get("market", pd.NA),
            "selection": bet.get("selection", pd.NA),
            "current_result_status": bet.get("result", "pending"),
            "suggested_result": suggested,
            "final_score": final_score,
            "reason": reason,
        })

    return pd.DataFrame(rows, columns=PREVIEW_COLUMNS)


def render_settlement_preview(preview: pd.DataFrame) -> str:
    if preview.empty:
        quick = "No pending ledger bets were found."
    else:
        counts = preview["suggested_result"].value_counts().to_dict()
        quick = ", ".join(f"{result}: {count}" for result, count in sorted(counts.items()))
    lines = [
        "# EPL Betting Lab Settlement Preview",
        "",
        "This report suggests results for pending manual ledger bets using finished match scores. It does not place bets, invent results, or update the ledger unless you run the settlement script with `--apply`.",
        "",
        "## Quick summary",
        "",
        f"- {quick}",
        "- `unmatched` means the helper did not find exactly one confident finished match.",
        "- Future matches stay pending/unmatched until finished results appear in the processed EPL data.",
        "",
        "## Preview",
        "",
        preview.to_markdown(index=False) if not preview.empty else "No pending bets to preview.",
    ]
    return "\n".join(lines)


def save_settlement_preview(preview: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "bet_settlement_preview.csv"
    markdown_path = output_dir / "bet_settlement_preview.md"
    preview.to_csv(csv_path, index=False)
    markdown_path.write_text(render_settlement_preview(preview), encoding="utf-8")
    return {"csv": csv_path, "markdown": markdown_path}


def apply_settlements_to_ledger(
    ledger: pd.DataFrame,
    preview: pd.DataFrame,
    unit_dollars: float = BANKROLL_UNIT_DOLLARS,
) -> tuple[pd.DataFrame, int]:
    if ledger.empty or preview.empty:
        return ledger.copy(), 0

    df = ledger.copy()
    for column in LEDGER_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    applied_indices = []
    result_map = preview.set_index("bet_id")["suggested_result"].to_dict()
    for index, row in df.iterrows():
        current_result = _clean_text(row.get("result")) or "pending"
        bet_id = row.get("bet_id")
        suggested = result_map.get(bet_id)
        if current_result != "pending" or suggested not in {"win", "loss", "push"}:
            continue
        df.at[index, "result"] = suggested
        applied_indices.append(index)

    if applied_indices:
        enriched = enrich_bet_ledger(df, unit_dollars=unit_dollars)
        for index in applied_indices:
            df.at[index, "profit_units"] = enriched.at[index, "profit_units"]
            df.at[index, "profit_dollars"] = enriched.at[index, "profit_dollars"]

    return df[LEDGER_COLUMNS], len(applied_indices)
