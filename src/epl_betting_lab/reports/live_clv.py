"""Closing-line value for the bets this card actually recommended.

The existing `reports/clv.py` measures backtested bets against Football-Data
closing prices. That is a real measurement of a different population: seasons
already in the dataset, scored by a rule tuned on them. This measures the live
card — the selections it published, at the price it published them, against
what the market did afterwards.

Why it matters more than profit here. Separating a true 5% edge from zero takes
roughly 1,500 settled bets, about twelve seasons at this rate, and the live
record currently holds 33. Every bet yields a CLV reading the moment its market
closes. And for the markets that carry this card it is the only feedback that
will ever exist: corners are 23 of the first 42 best bets and no source retains
their historical prices, so no corner rule can ever be profit-backtested.

Three honesties are built in.

**Nothing is called a closing price without saying how close it was.** Each row
carries `lead_minutes` — how long before kick-off the last observation was
taken. A reading four hours out is a later price, not a closing one, and the
report says which it has rather than letting the column name imply it.

**Two comparators, both named.** The card takes the best price across books, so
`clv_points_best` asks what the best price was at close — like for like, "did
the market move toward the bet I took". `clv_points_consensus` compares against
the de-vigged consensus, which is the conventional measure and is stricter,
because the best of several books is always longer than their fair midpoint.
Reporting one without naming it invites reading a mood as a measurement.

**Absence is a state, not a blank.** A pick with no later observation, a pick
whose fixture has not kicked off, and a pick from a card archived before event
ids were recorded are three different things and are counted as three.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from epl_betting_lab.reports.card_scoreboard import first_recommendations

#: Coverage states. Every staked pick lands in exactly one.
CAPTURED = "captured"
NO_LATER_PRICE = "no later observation before kick-off"
NOT_PLAYED = "fixture has not kicked off"
NO_KICKOFF = "kickoff unknown (card archived before kickoffs were recorded)"


def _implied(american: object) -> float | None:
    try:
        odds = float(american)
    except (TypeError, ValueError):
        return None
    if odds == 0:
        return None
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


def _key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """Join on the provider's event id where the card recorded one.

    Cards archived before 2026-09-02 carry no event id, so they fall back to
    normalised team names — weaker, and enough for a record that would
    otherwise be empty.
    """
    event = str(row.get("provider_event_id") or "").strip()
    identity = event or "{}|{}".format(
        str(row.get("home_team", "")).strip().casefold(),
        str(row.get("away_team", "")).strip().casefold(),
    )
    return (
        identity,
        str(row.get("market", "")).strip().casefold(),
        str(row.get("selection", "")).strip().casefold(),
    )


def _feed_keys(feed: pd.DataFrame) -> pd.DataFrame:
    frame = feed.copy()
    event = frame["provider_event_id"].fillna("").astype(str).str.strip()
    names = (
        frame["home_team"].fillna("").astype(str).str.strip().str.casefold()
        + "|"
        + frame["away_team"].fillna("").astype(str).str.strip().str.casefold()
    )
    frame["identity"] = event.where(event != "", names)
    frame["market_key"] = frame["market"].fillna("").astype(str).str.strip().str.casefold()
    frame["selection_key"] = frame["selection"].fillna("").astype(str).str.strip().str.casefold()
    frame["observed"] = pd.to_datetime(frame["observed_at"], errors="coerce", utc=True)
    frame["implied"] = frame["american_odds"].map(_implied)
    return frame.dropna(subset=["observed", "implied"])


def _consensus_implied(rows: pd.DataFrame, selection: str, siblings: pd.DataFrame) -> float | None:
    """De-vigged probability of `selection` from every book at one moment."""
    if rows.empty or siblings.empty:
        return None
    per_selection = siblings.groupby("selection_key")["implied"].mean()
    total = float(per_selection.sum())
    if total <= 0 or selection not in per_selection.index:
        return None
    return float(per_selection.loc[selection]) / total


#: Below this share of played picks captured, the feed is not doing its job.
MIN_CAPTURE_RATE = 0.5


def _coverage_warning(frame: pd.DataFrame) -> list[str]:
    """Say so when the capture is failing, because it fails silently.

    A snapshot that never fires and one that always fires after kick-off
    produce exactly the same thing here: an empty column. The weekly watchdog
    catches the first — a workflow that stops running leaves no successful run
    — and cannot catch the second, because those runs succeed. This is the
    check for the second, and it is the reason the report states a rate rather
    than only a mean.
    """
    if frame.empty:
        return []
    played = frame[frame["state"] != NOT_PLAYED]
    played = played[played["state"] != NO_KICKOFF]
    if played.empty:
        return []
    captured = int((played["state"] == CAPTURED).sum())
    rate = captured / len(played)
    if rate >= MIN_CAPTURE_RATE:
        return []
    return [
        f"> **Capture is failing: {captured} of {len(played)} played picks have a "
        f"price observed before kick-off.** A snapshot that never runs and one "
        "that always runs late look identical here, because an observation "
        "taken after kick-off is ignored rather than trusted. Check that the "
        "Closing Snapshot workflow is firing, and firing early enough — GitHub "
        "has delayed this repository's crons by nine hours before now.",
        "",
    ]


def build_live_clv(
    cards: Sequence[Mapping[str, Any]],
    feed: pd.DataFrame,
    *,
    now: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """One row per staked recommendation, with whatever the feed can say."""
    moment = now or pd.Timestamp.now(tz="UTC")
    keyed = _feed_keys(feed) if not feed.empty else pd.DataFrame()
    rows = []
    for pick in first_recommendations(cards):
        identity, market, selection = _key(pick)
        opened = pd.to_datetime(pick.get("first_seen"), errors="coerce", utc=True)
        kickoff = pd.to_datetime(pick.get("kickoff_time"), errors="coerce", utc=True)
        record: dict[str, Any] = {
            "home_team": pick.get("home_team"),
            "away_team": pick.get("away_team"),
            "market": market,
            "selection": selection,
            "selection_rule": pick.get("selection_rule") or "",
            "provider_event_id": pick.get("provider_event_id") or "",
            "suggested_units": pick.get("suggested_units"),
            "opening_american_odds": pick.get("american_odds"),
            "opening_implied": _implied(pick.get("american_odds")),
            "first_seen": pick.get("first_seen"),
            "kickoff_time": pick.get("kickoff_time"),
            "closing_american_odds": None,
            "closing_observed_at": None,
            "lead_minutes": None,
            "clv_points_best": None,
            "clv_points_consensus": None,
            "state": NO_LATER_PRICE,
        }
        if pd.isna(kickoff):
            record["state"] = NO_KICKOFF
            rows.append(record)
            continue
        if kickoff > moment:
            record["state"] = NOT_PLAYED
            rows.append(record)
            continue
        if keyed.empty:
            rows.append(record)
            continue
        window = keyed[
            (keyed["identity"] == identity)
            & (keyed["market_key"] == market)
            & (keyed["observed"] < kickoff)
        ]
        if not pd.isna(opened):
            window = window[window["observed"] > opened]
        mine = window[window["selection_key"] == selection]
        if mine.empty:
            rows.append(record)
            continue
        last_seen = mine["observed"].max()
        at_close = mine[mine["observed"] == last_seen]
        # The card takes the best price on offer, so the like-for-like question
        # is what the best price was at the close.
        best = at_close.loc[at_close["implied"].idxmin()]
        siblings = window[window["observed"] == last_seen]
        record.update({
            "closing_american_odds": best["american_odds"],
            "closing_observed_at": last_seen.isoformat(),
            "lead_minutes": round((kickoff - last_seen).total_seconds() / 60.0, 1),
            "state": CAPTURED,
        })
        opening_implied = record["opening_implied"]
        if opening_implied is not None:
            record["clv_points_best"] = round((float(best["implied"]) - opening_implied) * 100, 3)
            consensus = _consensus_implied(at_close, selection, siblings)
            if consensus is not None:
                record["clv_points_consensus"] = round((consensus - opening_implied) * 100, 3)
        rows.append(record)
    return pd.DataFrame(rows)


def summarize_live_clv(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-market coverage and CLV, counting what is missing as loudly as what is not."""
    if frame.empty:
        return pd.DataFrame(columns=["market", "picks", "captured", "clv_points_best", "clv_points_consensus"])
    rows = []
    for market, group in frame.groupby("market"):
        captured = group[group["state"] == CAPTURED]
        rows.append({
            "market": market,
            "picks": int(len(group)),
            "captured": int(len(captured)),
            "awaiting_kickoff": int((group["state"] == NOT_PLAYED).sum()),
            "no_later_price": int((group["state"] == NO_LATER_PRICE).sum()),
            "kickoff_unknown": int((group["state"] == NO_KICKOFF).sum()),
            "clv_points_best": round(float(captured["clv_points_best"].mean()), 3) if len(captured) else None,
            "clv_points_consensus": round(float(captured["clv_points_consensus"].mean()), 3) if captured["clv_points_consensus"].notna().any() else None,
            "beat_the_close": int((captured["clv_points_best"] > 0).sum()) if len(captured) else 0,
        })
    return pd.DataFrame(rows).sort_values("picks", ascending=False).reset_index(drop=True)


def render_live_clv(frame: pd.DataFrame, summary: pd.DataFrame) -> str:
    captured = frame[frame["state"] == CAPTURED] if not frame.empty else frame
    lines = [
        "# Live closing-line value",
        "",
        "The card's own recommendations, at the price the card published, against",
        "what the market did afterwards. Distinct from `clv_report.md`, which",
        "measures backtested bets against Football-Data closes for seasons already",
        "in the dataset — a real measurement of a different population.",
        "",
        f"Staked picks on file: **{len(frame)}**. With a later price captured: "
        f"**{len(captured)}**.",
        "",
    ]
    if len(captured):
        lead = captured["lead_minutes"].dropna()
        if len(lead):
            lines += [
                f"Last observation before kick-off, median **{lead.median():.0f} minutes** "
                f"out (range {lead.min():.0f}–{lead.max():.0f}). A reading hours before "
                "kick-off is a later price, not a closing one; read the number with "
                "the lead time beside it.",
                "",
            ]
    else:
        lines += [
            "**No closing observations yet.** The feed starts collecting from the "
            "first run after it was added, so this fills in from the next "
            "matchday onward. That is a gap in the record and not a judgement "
            "about the model.",
            "",
        ]
    lines += _coverage_warning(frame)
    lines += [
        "`clv_points_best` compares against the best price across books at the last",
        "observation — like for like, since the card takes the best price.",
        "`clv_points_consensus` compares against the de-vigged consensus, which is",
        "the conventional and stricter measure. Positive means the market moved",
        "toward the bet.",
        "",
        summary.to_markdown(index=False) if not summary.empty else "_No picks on file._",
        "",
    ]
    return "\n".join(lines)


def save_live_clv_reports(
    cards: Sequence[Mapping[str, Any]],
    feed: pd.DataFrame,
    output_dir: Path,
    *,
    now: pd.Timestamp | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame = build_live_clv(cards, feed, now=now)
    summary = summarize_live_clv(frame)
    paths = {
        "detail": output_dir / "live_clv_bets.csv",
        "summary": output_dir / "live_clv_by_market.csv",
        "markdown": output_dir / "live_clv_report.md",
    }
    frame.to_csv(paths["detail"], index=False)
    summary.to_csv(paths["summary"], index=False)
    paths["markdown"].write_text(render_live_clv(frame, summary), encoding="utf-8")
    return paths
