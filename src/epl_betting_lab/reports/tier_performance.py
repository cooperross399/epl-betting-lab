from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR, OUTPUTS_DIR
from epl_betting_lab.reports.bet_ledger import enrich_bet_ledger


TIER_ORDER = {"A": 0, "B": 1, "C": 2, "LEAN": 3, "Pass/Avoid": 4, "Unknown": 5}
OUTPUT_COLUMNS = [
    "confidence_tier",
    "recommendation_status",
    "tracked_recommendations",
    "actual_bets",
    "settled_bets",
    "wins",
    "losses",
    "pushes",
    "pending_bets",
    "tracking_only_recommendations",
    "units_won_lost",
    "roi",
    "avg_american_odds",
    "avg_suggested_units",
    "avg_actual_stake_units",
    "bets_with_clv",
    "avg_clv_probability_points",
]


def _empty_performance(group_cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=group_cols + OUTPUT_COLUMNS[2:])


def _clean_text(value: object, default: str = "") -> str:
    if pd.isna(value):
        return default
    text = str(value).strip()
    return text if text else default


def _normal_status(value: object) -> str:
    text = _clean_text(value, "PASS/Avoid")
    upper = text.upper()
    if upper == "BETTABLE":
        return "BETTABLE"
    if upper == "LEAN":
        return "LEAN"
    if "PASS" in upper or "AVOID" in upper:
        return "PASS/Avoid"
    return text


def _normal_tier(value: object, status: object = "") -> str:
    text = _clean_text(value)
    upper = text.upper()
    if upper in {"A", "B", "C"}:
        return upper
    if upper == "LEAN":
        return "LEAN"
    if "PASS" in upper or "AVOID" in upper:
        return "Pass/Avoid"
    if _normal_status(status) == "LEAN":
        return "LEAN"
    if _normal_status(status) == "PASS/Avoid":
        return "Pass/Avoid"
    return "Unknown"


def _odds_range(odds: object) -> str:
    value = pd.to_numeric(odds, errors="coerce")
    if pd.isna(value):
        return "missing odds"
    value = float(value)
    if value <= -160:
        return "-160 or worse"
    if value < -120:
        return "-159 to -121"
    if value <= 100:
        return "-120 to +100"
    if value <= 150:
        return "+101 to +150"
    return "+151 or longer"


def _archive_root(output_dir: Path) -> Path:
    return output_dir / "archive" / "thursday_best_bets"


def _read_archived_recommendations(output_dir: Path) -> pd.DataFrame:
    archive_root = _archive_root(output_dir)
    csv_paths = sorted(archive_root.glob("*/*_thursday_best_bets.csv"))
    if not csv_paths:
        return pd.DataFrame()

    frames = []
    for path in csv_paths:
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if df.empty:
            continue
        df = df.copy()
        df["archive_csv"] = str(path)
        df["archive_date"] = path.parent.name
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _recommendation_key(df: pd.DataFrame) -> pd.Series:
    pieces = []
    for column in ["home_team", "away_team", "market", "selection"]:
        if column not in df.columns:
            pieces.append(pd.Series([""] * len(df), index=df.index))
        else:
            pieces.append(df[column].fillna("").astype(str).str.strip().str.lower())
    return pieces[0] + "|" + pieces[1] + "|" + pieces[2] + "|" + pieces[3]


def _latest_archive_lookup(archives: pd.DataFrame) -> pd.DataFrame:
    if archives.empty:
        return pd.DataFrame(columns=["_key", "confidence_tier", "status", "suggested_units"])
    df = archives.copy()
    for column in ["confidence_tier", "status", "suggested_units"]:
        if column not in df.columns:
            df[column] = pd.NA
    df["_key"] = _recommendation_key(df)
    return df.drop_duplicates("_key", keep="last")[["_key", "confidence_tier", "status", "suggested_units"]]


def _prepare_ledger_rows(ledger_path: Path, archives: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    notes: list[str] = []
    if not ledger_path.exists():
        notes.append("Missing bet ledger: no actual placed bets are available yet.")
        return pd.DataFrame(), notes

    ledger = pd.read_csv(ledger_path)
    if ledger.empty:
        notes.append("The bet ledger exists, but it has no bet rows yet.")
        return pd.DataFrame(), notes
    enriched = enrich_bet_ledger(ledger)
    enriched["_key"] = _recommendation_key(enriched)

    lookup = _latest_archive_lookup(archives)
    if not lookup.empty:
        enriched = enriched.merge(lookup, how="left", on="_key", suffixes=("", "_archive"))

    if "confidence_tier" not in enriched.columns:
        enriched["confidence_tier"] = pd.NA
    if "status" not in enriched.columns:
        enriched["status"] = pd.NA
    if "suggested_units" not in enriched.columns:
        enriched["suggested_units"] = pd.NA

    for column in ["confidence_tier_archive", "status_archive", "suggested_units_archive"]:
        if column not in enriched.columns:
            enriched[column] = pd.NA
    enriched["confidence_tier"] = enriched["confidence_tier"].combine_first(enriched["confidence_tier_archive"])
    enriched["status"] = enriched["status"].combine_first(enriched["status_archive"])
    enriched["suggested_units"] = enriched["suggested_units"].combine_first(enriched["suggested_units_archive"])
    if enriched["confidence_tier"].isna().all():
        notes.append("No confidence_tier column was found in the ledger, and no matching archived recommendation supplied one.")

    rows = pd.DataFrame({
        "source_type": "actual_bet",
        "confidence_tier": [
            _normal_tier(tier, status)
            for tier, status in zip(enriched["confidence_tier"], enriched["model_recommendation_status"], strict=False)
        ],
        "recommendation_status": enriched["model_recommendation_status"].apply(_normal_status),
        "market": enriched["market"].fillna(""),
        "selection": enriched["selection"].fillna(""),
        "home_team": enriched["home_team"].fillna(""),
        "away_team": enriched["away_team"].fillna(""),
        "american_odds": pd.to_numeric(enriched["american_odds"], errors="coerce"),
        "closing_american_odds": pd.to_numeric(enriched["closing_american_odds"], errors="coerce"),
        "suggested_units": pd.to_numeric(enriched["suggested_units"], errors="coerce"),
        "actual_stake_units": pd.to_numeric(enriched["stake_units"], errors="coerce"),
        "result": enriched["result"],
        "profit_units": pd.to_numeric(enriched["profit_units"], errors="coerce"),
        "clv_probability_points": pd.to_numeric(enriched["clv_probability_points"], errors="coerce"),
        "is_settled": enriched["is_settled"],
        "is_pending": enriched["is_pending"],
    })
    return rows, notes


def _prepare_archive_rows(archives: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    notes: list[str] = []
    if archives.empty:
        notes.append("No archived Thursday best-bets reports were found for recommendation tracking.")
        return pd.DataFrame(), notes

    df = archives.copy()
    for column in ["confidence_tier", "status", "market", "selection", "home_team", "away_team", "american_odds", "suggested_units"]:
        if column not in df.columns:
            df[column] = pd.NA
    if "confidence_tier" not in archives.columns:
        notes.append("Archived reports do not have a confidence_tier column yet.")

    rows = pd.DataFrame({
        "source_type": "recommendation_tracking_only",
        "confidence_tier": [_normal_tier(tier, status) for tier, status in zip(df["confidence_tier"], df["status"], strict=False)],
        "recommendation_status": df["status"].apply(_normal_status),
        "market": df["market"].fillna(""),
        "selection": df["selection"].fillna(""),
        "home_team": df["home_team"].fillna(""),
        "away_team": df["away_team"].fillna(""),
        "american_odds": pd.to_numeric(df["american_odds"], errors="coerce"),
        "closing_american_odds": pd.NA,
        "suggested_units": pd.to_numeric(df["suggested_units"], errors="coerce"),
        "actual_stake_units": pd.NA,
        "result": "tracking_only",
        "profit_units": pd.NA,
        "clv_probability_points": pd.NA,
        "is_settled": False,
        "is_pending": False,
    })
    return rows, notes


def load_tier_performance_source(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    output_dir = output_dir or OUTPUTS_DIR
    ledger_path = ledger_path or MANUAL_DIR / "bet_ledger.csv"
    archives = _read_archived_recommendations(output_dir)
    ledger_rows, ledger_notes = _prepare_ledger_rows(ledger_path, archives)
    archive_rows, archive_notes = _prepare_archive_rows(archives)
    combined = pd.concat([ledger_rows, archive_rows], ignore_index=True)
    if combined.empty:
        return combined, ledger_notes + archive_notes
    combined["odds_range"] = combined["american_odds"].apply(_odds_range)
    combined["has_clv"] = combined["clv_probability_points"].notna()
    combined["is_actual_bet"] = combined["source_type"] == "actual_bet"
    combined["is_tracking_only"] = combined["source_type"] == "recommendation_tracking_only"
    return combined, ledger_notes + archive_notes


def summarize_tier_performance(source: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    if source.empty:
        return _empty_performance(group_cols)

    rows = []
    for key, group in source.groupby(group_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        actual = group[group["is_actual_bet"]]
        settled = actual[actual["is_settled"]]
        stake = pd.to_numeric(settled["actual_stake_units"], errors="coerce").fillna(1.0)
        profit = pd.to_numeric(settled["profit_units"], errors="coerce").fillna(0.0)
        row = dict(zip(group_cols, key, strict=False))
        row.update({
            "tracked_recommendations": int(len(group)),
            "actual_bets": int(len(actual)),
            "settled_bets": int(len(settled)),
            "wins": int((settled["result"] == "win").sum()),
            "losses": int((settled["result"] == "loss").sum()),
            "pushes": int((settled["result"] == "push").sum()),
            "pending_bets": int((actual["result"] == "pending").sum()) if not actual.empty else 0,
            "tracking_only_recommendations": int(group["is_tracking_only"].sum()),
            "units_won_lost": round(float(profit.sum()), 3),
            "roi": round(float(profit.sum()) / float(stake.sum()), 3) if float(stake.sum()) else 0.0,
            "avg_american_odds": round(float(pd.to_numeric(group["american_odds"], errors="coerce").mean()), 1)
            if group["american_odds"].notna().any()
            else pd.NA,
            "avg_suggested_units": round(float(pd.to_numeric(group["suggested_units"], errors="coerce").mean()), 3)
            if group["suggested_units"].notna().any()
            else pd.NA,
            "avg_actual_stake_units": round(float(stake.mean()), 3) if not settled.empty else pd.NA,
            "bets_with_clv": int(actual["clv_probability_points"].notna().sum()) if not actual.empty else 0,
            "avg_clv_probability_points": round(float(actual["clv_probability_points"].mean()), 4)
            if actual["clv_probability_points"].notna().any()
            else pd.NA,
        })
        rows.append(row)

    out = pd.DataFrame(rows)
    if "confidence_tier" in out.columns:
        out["_tier_order"] = out["confidence_tier"].map(TIER_ORDER).fillna(99)
        out = out.sort_values(["_tier_order", "units_won_lost", "tracked_recommendations"], ascending=[True, True, False])
        out = out.drop(columns=["_tier_order"])
    return out[group_cols + OUTPUT_COLUMNS[2:]]


def build_team_tier_performance(source: pd.DataFrame) -> pd.DataFrame:
    if source.empty:
        return _empty_performance(["confidence_tier", "recommendation_status", "team", "team_role"])
    rows = []
    for _, row in source.iterrows():
        home = row.to_dict()
        home["team"] = row.get("home_team", "")
        home["team_role"] = "home"
        rows.append(home)
        away = row.to_dict()
        away["team"] = row.get("away_team", "")
        away["team_role"] = "away"
        rows.append(away)
    expanded = pd.DataFrame(rows)
    return summarize_tier_performance(expanded, ["confidence_tier", "recommendation_status", "team", "team_role"])


def _conclusions(summary: pd.DataFrame, by_market: pd.DataFrame, source: pd.DataFrame, notes: list[str]) -> list[str]:
    conclusions = []
    settled = int(summary["settled_bets"].sum()) if not summary.empty else 0
    if settled == 0:
        conclusions.append("No settled bets yet, so tier profitability is not proven. Treat this as recommendation tracking only for now.")
    else:
        profitable = summary[(summary["settled_bets"] > 0) & (summary["units_won_lost"] > 0)]
        leaking = summary[(summary["settled_bets"] > 0) & (summary["units_won_lost"] < 0)]
        conclusions.append(
            "Profitable tiers: "
            + (", ".join(profitable["confidence_tier"].astype(str).unique()) if not profitable.empty else "none yet")
            + "."
        )
        conclusions.append(
            "Leaking tiers: "
            + (", ".join(leaking["confidence_tier"].astype(str).unique()) if not leaking.empty else "none yet")
            + "."
        )

    if not by_market.empty and int(by_market["settled_bets"].sum()) > 0:
        trusted = by_market[(by_market["settled_bets"] > 0) & (by_market["units_won_lost"] > 0)]
        restricted = by_market[(by_market["settled_bets"] > 0) & (by_market["units_won_lost"] < 0)]
        conclusions.append(
            "Markets showing profit: "
            + (", ".join(sorted(trusted["market"].astype(str).unique())) if not trusted.empty else "none yet")
            + "."
        )
        conclusions.append(
            "Markets to restrict: "
            + (", ".join(sorted(restricted["market"].astype(str).unique())) if not restricted.empty else "none yet")
            + "."
        )
    else:
        conclusions.append("No market has enough settled ledger evidence yet; keep using backtests and CLV as supporting evidence.")

    c_rows = source[source["confidence_tier"] == "C"] if not source.empty else pd.DataFrame()
    if c_rows.empty or int(c_rows.get("is_settled", pd.Series(dtype=bool)).sum()) == 0:
        conclusions.append("C-tier should remain watchlist-only until settled ledger evidence says otherwise.")
    under_rows = source[(source["market"] == "total_2_5") & (source["selection"].astype(str).str.lower() == "under")] if not source.empty else pd.DataFrame()
    if under_rows.empty or int(under_rows.get("is_settled", pd.Series(dtype=bool)).sum()) == 0:
        conclusions.append("Totals unders should remain protected; there is not enough settled tier evidence to loosen the guardrails.")
    conclusions.extend(notes)
    return conclusions


def render_tier_performance_report(
    summary: pd.DataFrame,
    by_market: pd.DataFrame,
    by_team: pd.DataFrame,
    by_odds_range: pd.DataFrame,
    by_clv: pd.DataFrame,
    source: pd.DataFrame,
    notes: list[str],
) -> str:
    conclusions = _conclusions(summary, by_market, source, notes)
    lines = [
        "# Tier Performance Report",
        "",
        "This report reviews confidence tiers from the manual bet ledger and archived Thursday reports. It does not fetch odds, fabricate prices, place bets, or edit manual files.",
        "",
        "## Plain-English conclusions",
        "",
    ]
    lines.extend([f"- {item}" for item in conclusions])
    lines.extend([
        "",
        "## How to read this",
        "",
        "- Actual settled ledger bets count toward wins, losses, pushes, units, and ROI.",
        "- Pending bets do not count toward profit/loss or ROI.",
        "- Archived Thursday rows without a matching placed bet are marked as recommendation tracking only.",
        "- CLV stays blank unless closing odds or `clv_probability_points` are available.",
        "",
        "## Tier summary",
        "",
        summary.to_markdown(index=False) if not summary.empty else "No tier rows available yet.",
        "",
        "## By market",
        "",
        by_market.to_markdown(index=False) if not by_market.empty else "No market rows available yet.",
        "",
        "## By team",
        "",
        by_team.to_markdown(index=False) if not by_team.empty else "No team rows available yet.",
        "",
        "## By odds range",
        "",
        by_odds_range.to_markdown(index=False) if not by_odds_range.empty else "No odds range rows available yet.",
        "",
        "## By CLV",
        "",
        by_clv.to_markdown(index=False) if not by_clv.empty else "No closing-line value rows available yet.",
    ])
    return "\n".join(lines)


def save_tier_performance_reports(
    ledger_path: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    output_dir = output_dir or OUTPUTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    source, notes = load_tier_performance_source(ledger_path, output_dir)
    summary = summarize_tier_performance(source, ["confidence_tier", "recommendation_status"])
    by_market = summarize_tier_performance(source, ["confidence_tier", "recommendation_status", "market", "selection"])
    by_team = build_team_tier_performance(source)
    by_odds_range = summarize_tier_performance(source, ["confidence_tier", "recommendation_status", "odds_range"])
    clv_source = source[source["clv_probability_points"].notna()] if not source.empty else source
    by_clv = summarize_tier_performance(clv_source, ["confidence_tier", "recommendation_status", "market"]) if not clv_source.empty else _empty_performance(["confidence_tier", "recommendation_status", "market"])

    paths = {
        "summary": output_dir / "tier_performance_summary.csv",
        "market": output_dir / "tier_performance_by_market.csv",
        "team": output_dir / "tier_performance_by_team.csv",
        "odds_range": output_dir / "tier_performance_by_odds_range.csv",
        "clv": output_dir / "tier_performance_by_clv.csv",
        "markdown": output_dir / "tier_performance_report.md",
    }
    summary.to_csv(paths["summary"], index=False)
    by_market.to_csv(paths["market"], index=False)
    by_team.to_csv(paths["team"], index=False)
    by_odds_range.to_csv(paths["odds_range"], index=False)
    by_clv.to_csv(paths["clv"], index=False)
    paths["markdown"].write_text(
        render_tier_performance_report(summary, by_market, by_team, by_odds_range, by_clv, source, notes),
        encoding="utf-8",
    )
    return paths
