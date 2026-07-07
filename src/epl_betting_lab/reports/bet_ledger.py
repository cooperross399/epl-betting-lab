from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import BANKROLL_UNIT_DOLLARS
from epl_betting_lab.models.value import american_to_implied


LEDGER_COLUMNS = [
    "bet_id",
    "date",
    "season",
    "match",
    "home_team",
    "away_team",
    "market",
    "selection",
    "model_recommendation_status",
    "raw_model_prob",
    "calibrated_model_prob",
    "raw_edge",
    "calibrated_edge",
    "american_odds",
    "closing_american_odds",
    "stake_units",
    "stake_dollars",
    "result",
    "profit_units",
    "profit_dollars",
    "clv_probability_points",
    "book",
    "notes",
]

RESULTS = {"win", "loss", "push", "pending"}


def empty_ledger() -> pd.DataFrame:
    return pd.DataFrame(columns=LEDGER_COLUMNS)


def ensure_ledger_template(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        empty_ledger().to_csv(path, index=False)
    return path


def load_bet_ledger(path: Path) -> pd.DataFrame:
    if not path.exists():
        return empty_ledger()
    ledger = pd.read_csv(path)
    for column in LEDGER_COLUMNS:
        if column not in ledger.columns:
            ledger[column] = pd.NA
    return ledger[LEDGER_COLUMNS].copy()


def _clean_result(result: object) -> str:
    if pd.isna(result) or str(result).strip() == "":
        return "pending"
    cleaned = str(result).strip().lower()
    if cleaned not in RESULTS:
        raise ValueError(f"Unsupported result '{result}'. Use win, loss, push, or pending.")
    return cleaned


def _profit_units(stake_units: object, american_odds: object, result: str, entered_profit: object) -> float | pd.NA:
    if result == "pending":
        return pd.NA
    if pd.notna(entered_profit) and str(entered_profit).strip() != "":
        return round(float(entered_profit), 3)

    stake = float(stake_units) if pd.notna(stake_units) and str(stake_units).strip() != "" else 1.0
    if result == "push":
        return 0.0
    if result == "loss":
        return round(-stake, 3)

    odds = float(american_odds)
    if odds > 0:
        return round(stake * odds / 100, 3)
    return round(stake * 100 / abs(odds), 3)


def _profit_dollars(profit_units: object, entered_profit_dollars: object, unit_dollars: float) -> float | pd.NA:
    if pd.notna(entered_profit_dollars) and str(entered_profit_dollars).strip() != "":
        return round(float(entered_profit_dollars), 2)
    if pd.isna(profit_units):
        return pd.NA
    return round(float(profit_units) * unit_dollars, 2)


def _clv_probability_points(opening_odds: object, closing_odds: object, entered_clv: object) -> float | pd.NA:
    if pd.notna(entered_clv) and str(entered_clv).strip() != "":
        return round(float(entered_clv), 4)
    if pd.isna(opening_odds) or pd.isna(closing_odds):
        return pd.NA
    if str(opening_odds).strip() == "" or str(closing_odds).strip() == "":
        return pd.NA
    return round(american_to_implied(float(closing_odds)) - american_to_implied(float(opening_odds)), 4)


def enrich_bet_ledger(ledger: pd.DataFrame, unit_dollars: float = BANKROLL_UNIT_DOLLARS) -> pd.DataFrame:
    if ledger.empty:
        return empty_ledger().assign(
            is_settled=pd.Series(dtype=bool),
            is_pending=pd.Series(dtype=bool),
            has_closing_odds=pd.Series(dtype=bool),
            opening_implied_probability=pd.Series(dtype=float),
            closing_implied_probability=pd.Series(dtype=float),
        )

    df = ledger.copy()
    for column in LEDGER_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA

    numeric_columns = [
        "raw_model_prob",
        "calibrated_model_prob",
        "raw_edge",
        "calibrated_edge",
        "american_odds",
        "closing_american_odds",
        "stake_units",
        "stake_dollars",
        "profit_units",
        "profit_dollars",
        "clv_probability_points",
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["result"] = df["result"].apply(_clean_result)
    df["is_pending"] = df["result"] == "pending"
    df["is_settled"] = ~df["is_pending"]
    df["has_closing_odds"] = df["closing_american_odds"].notna()
    df["opening_implied_probability"] = df["american_odds"].apply(
        lambda odds: american_to_implied(odds) if pd.notna(odds) else pd.NA
    )
    df["closing_implied_probability"] = df["closing_american_odds"].apply(
        lambda odds: american_to_implied(odds) if pd.notna(odds) else pd.NA
    )

    df["profit_units"] = df.apply(
        lambda row: _profit_units(row["stake_units"], row["american_odds"], row["result"], row["profit_units"]),
        axis=1,
    )
    df["profit_dollars"] = df.apply(
        lambda row: _profit_dollars(row["profit_units"], row["profit_dollars"], unit_dollars),
        axis=1,
    )
    df["clv_probability_points"] = df.apply(
        lambda row: _clv_probability_points(
            row["american_odds"], row["closing_american_odds"], row["clv_probability_points"]
        ),
        axis=1,
    )
    return df


def summarize_overall(ledger: pd.DataFrame) -> dict[str, object]:
    df = enrich_bet_ledger(ledger)
    settled = df[df["is_settled"]].copy()
    pending = df[df["is_pending"]].copy()
    settled_stake = float(settled["stake_units"].fillna(1.0).sum()) if not settled.empty else 0.0
    profit_units = float(settled["profit_units"].fillna(0.0).sum()) if not settled.empty else 0.0

    clv_rows = df[df["clv_probability_points"].notna()]
    return {
        "tracked_bets": int(len(df)),
        "settled_bets": int(len(settled)),
        "pending_bets": int(len(pending)),
        "wins": int((settled["result"] == "win").sum()) if not settled.empty else 0,
        "losses": int((settled["result"] == "loss").sum()) if not settled.empty else 0,
        "pushes": int((settled["result"] == "push").sum()) if not settled.empty else 0,
        "profit_units": round(profit_units, 3),
        "roi": round(profit_units / settled_stake, 3) if settled_stake else 0.0,
        "bets_with_clv": int(len(clv_rows)),
        "avg_clv_probability_points": round(float(clv_rows["clv_probability_points"].mean()), 4)
        if not clv_rows.empty
        else pd.NA,
    }


def summarize_ledger_by(ledger: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    columns = group_cols + [
        "tracked_bets",
        "settled_bets",
        "wins",
        "losses",
        "pushes",
        "pending_bets",
        "profit_units",
        "roi",
        "avg_clv_probability_points",
    ]
    df = enrich_bet_ledger(ledger)
    if df.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for key, group in df.groupby(group_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        settled = group[group["is_settled"]]
        settled_stake = float(settled["stake_units"].fillna(1.0).sum()) if not settled.empty else 0.0
        profit = float(settled["profit_units"].fillna(0.0).sum()) if not settled.empty else 0.0
        clv_rows = group[group["clv_probability_points"].notna()]
        row = dict(zip(group_cols, key, strict=False))
        row.update({
            "tracked_bets": int(len(group)),
            "settled_bets": int(len(settled)),
            "wins": int((settled["result"] == "win").sum()) if not settled.empty else 0,
            "losses": int((settled["result"] == "loss").sum()) if not settled.empty else 0,
            "pushes": int((settled["result"] == "push").sum()) if not settled.empty else 0,
            "pending_bets": int((group["result"] == "pending").sum()),
            "profit_units": round(profit, 3),
            "roi": round(profit / settled_stake, 3) if settled_stake else 0.0,
            "avg_clv_probability_points": round(float(clv_rows["clv_probability_points"].mean()), 4)
            if not clv_rows.empty
            else pd.NA,
        })
        rows.append(row)

    return pd.DataFrame(rows, columns=columns).sort_values(["profit_units", "tracked_bets"], ascending=[True, False])


def build_team_breakdown(ledger: pd.DataFrame) -> pd.DataFrame:
    df = enrich_bet_ledger(ledger)
    if df.empty:
        return pd.DataFrame(columns=["team", "team_role"] + summarize_ledger_by(df, ["market"]).columns.tolist()[1:])

    rows = []
    for _, bet in df.iterrows():
        home = bet.to_dict()
        home["team"] = bet["home_team"]
        home["team_role"] = "home"
        rows.append(home)

        away = bet.to_dict()
        away["team"] = bet["away_team"]
        away["team_role"] = "away"
        rows.append(away)

    return summarize_ledger_by(pd.DataFrame(rows), ["team", "team_role"])


def pending_bets(ledger: pd.DataFrame) -> pd.DataFrame:
    df = enrich_bet_ledger(ledger)
    columns = [
        "bet_id",
        "date",
        "match",
        "market",
        "selection",
        "american_odds",
        "stake_units",
        "book",
        "notes",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    return df[df["is_pending"]][columns].copy()


def render_bet_ledger_summary(
    overall: dict[str, object],
    by_market: pd.DataFrame,
    by_selection: pd.DataFrame,
    by_team: pd.DataFrame,
    pending: pd.DataFrame,
) -> str:
    clv_line = (
        f"{overall['bets_with_clv']} bets have CLV. Average CLV is "
        f"{float(overall['avg_clv_probability_points']):.2%} probability points."
        if pd.notna(overall["avg_clv_probability_points"])
        else "No bets have closing odds yet, so CLV is blank instead of guessed."
    )
    record = f"{overall['wins']}-{overall['losses']}-{overall['pushes']}"
    lines = [
        "# EPL Betting Lab Bet Ledger Summary",
        "",
        "This report summarizes manually entered bets. It does not fetch live odds, invent prices, or place bets.",
        "",
        "## Overall",
        "",
        f"- Record: {record} with {overall['pending_bets']} pending bets.",
        f"- Profit/loss: {overall['profit_units']} units.",
        f"- ROI: {overall['roi']:.1%} using settled stake units only.",
        f"- CLV: {clv_line}",
        "- Pending bets do not count toward profit/loss or ROI.",
        "- Pushes count as 0 profit/loss.",
        "",
        "## By market",
        "",
        by_market.to_markdown(index=False) if not by_market.empty else "No bets entered yet.",
        "",
        "## By selection",
        "",
        by_selection.to_markdown(index=False) if not by_selection.empty else "No bets entered yet.",
        "",
        "## By team",
        "",
        by_team.to_markdown(index=False) if not by_team.empty else "No bets entered yet.",
        "",
        "## Pending bets",
        "",
        pending.to_markdown(index=False) if not pending.empty else "No pending bets.",
    ]
    return "\n".join(lines)


def save_bet_ledger_reports(ledger: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    enriched = enrich_bet_ledger(ledger)
    reports = {
        "market": summarize_ledger_by(enriched, ["market"]),
        "selection": summarize_ledger_by(enriched, ["market", "selection"]),
        "team": build_team_breakdown(enriched),
        "pending": pending_bets(enriched),
    }

    paths = {
        "market": output_dir / "bet_ledger_by_market.csv",
        "selection": output_dir / "bet_ledger_by_selection.csv",
        "team": output_dir / "bet_ledger_by_team.csv",
        "pending": output_dir / "bet_ledger_pending.csv",
    }
    for name, report in reports.items():
        report.to_csv(paths[name], index=False)

    paths["markdown"] = output_dir / "bet_ledger_summary.md"
    paths["markdown"].write_text(
        render_bet_ledger_summary(
            summarize_overall(enriched),
            reports["market"],
            reports["selection"],
            reports["team"],
            reports["pending"],
        ),
        encoding="utf-8",
    )
    return paths
