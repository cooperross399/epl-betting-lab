"""Player-prop picks for the card, held by policy until a review says
otherwise.

This is the props counterpart of the automated card input: it reads the
props staging file, prices every staged outcome with the calibrated player
model, and emits picks — but only for prop markets the reviewed provider
policy lists in `required_markets`. Until an approval adds them, the report
states **Held by policy** and emits nothing, which is a decision on record,
never a "no value found".

The probability applied is the corrected one. The correction constants ship
here from the held-out validation of 2026-08-22 (PR #237): fitted on
February–March 2026 and proven on April–May it never saw, where it
straightened every volume bucket. Refit them when the measurement is rerun
on more history; do not tune them by hand.

Stakes are deliberately the smallest the card uses and the edge bar is
deliberately above the match-level bars, because the model prices the
morning and books reprice on the team sheet at T-75 minutes — a structural
deficit no fetch can close. The standing measurement demonstrates no edge
(about two qualifying picks a month); that sentence belongs in front of
every reader of this report, so the report carries it.

Never fabricates a price, never writes staging or manual files, never
places a bet, never applies settlement.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import (
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    STAGING_DIR,
)
from epl_betting_lab.models.player_props import (
    PlayerPropsModel,
    PropCalibration,
)
from epl_betting_lab.providers.player_props_staging import (
    PROP_EVENT_MARKETS,
    PROPS_STAGING_FILENAME,
)
from epl_betting_lab.reports.player_props_backtest import (
    SETTLEMENT_COLUMNS,
    _implied_probability,
    _parse_selection,
)


CARD_JSON_FILENAME = "player_props_card.json"
CARD_MARKDOWN_FILENAME = "player_props_card.md"

HELD_STATUS = "Held by policy"
READY_STATUS = "Props card ready"
NO_STAGING_STATUS = "No props staging evidence"

#: The correction proven on held-out data (PR #237). Refit by rerunning the
#: measurement with a split; never hand-tune.
SHIPPED_CORRECTION = PropCalibration(
    intercept=-0.2383, slope=0.9133, fitted_on=7254
)

#: Above every match-level bar, for the team-sheet deficit.
PROPS_EDGE_THRESHOLD = 0.08

#: The smallest stake the card uses anywhere. Props have no demonstrated
#: edge; a larger number would imply one.
PROPS_UNITS = 0.1


@dataclass(frozen=True)
class PropPick:
    date: str
    home_team: str
    away_team: str
    market: str
    player: str
    selection: str
    model_probability: float
    implied_probability: float
    edge: float
    american_odds: float
    book: str
    units: float


def approved_prop_markets(policy_path: Path | None = None) -> list[str]:
    """Prop markets the reviewed policy has approved. Empty means held."""
    path = (
        Path(policy_path)
        if policy_path
        else PROJECT_ROOT / "data" / "manual" / "staging_provider_policy.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    entries = payload.get("provider_allowlist_entries")
    if not isinstance(entries, Mapping):
        return []
    approved: set[str] = set()
    for entry in entries.values():
        if not isinstance(entry, Mapping):
            continue
        markets = entry.get("required_markets")
        if isinstance(markets, list):
            approved.update(str(item).strip() for item in markets)
    return [m for m in PROP_EVENT_MARKETS if m in approved]


def build_player_props_card(
    *,
    props_staging_path: Path | None = None,
    logs_path: Path | None = None,
    policy_path: Path | None = None,
    run_at: datetime | None = None,
    edge_threshold: float = PROPS_EDGE_THRESHOLD,
    correction: PropCalibration = SHIPPED_CORRECTION,
) -> dict[str, object]:
    staging = (
        Path(props_staging_path)
        if props_staging_path
        else Path(STAGING_DIR) / PROPS_STAGING_FILENAME
    )
    logs_file = (
        Path(logs_path)
        if logs_path
        else Path(PROCESSED_DIR) / "player_match_logs.csv"
    )
    moment = run_at or datetime.now().astimezone()
    today = moment.strftime("%Y-%m-%d")

    approved = approved_prop_markets(policy_path)
    summary: dict[str, object] = {
        "generated_at": moment.isoformat(timespec="seconds"),
        "approved_prop_markets": approved,
        "held_prop_markets": [
            m for m in PROP_EVENT_MARKETS if m not in approved
        ],
        "edge_threshold": edge_threshold,
        "units_per_pick": PROPS_UNITS,
        "correction": {
            "intercept": correction.intercept,
            "slope": correction.slope,
            "fitted_on": correction.fitted_on,
        },
        "markets_with_staged_prices": [],
        "picks": [],
        "safety": {
            "prices_fabricated": False,
            "bets_placed": False,
            "settlement_applied": False,
            "protected_files_written": False,
        },
    }

    if not approved:
        # Held is not blind: which prop markets hold staged prices is
        # evidence a future approval binds to, so it is reported even while
        # nothing is priced.
        if staging.is_file():
            try:
                staged = pd.read_csv(staging, dtype=str)
                summary["markets_with_staged_prices"] = sorted(
                    set(staged.get("market", pd.Series(dtype=str)).dropna())
                    & set(PROP_EVENT_MARKETS)
                )
            except (OSError, UnicodeError, pd.errors.ParserError):
                pass
        summary["status"] = HELD_STATUS
        summary["note"] = (
            "Every prop market is held by the reviewed provider policy. "
            "Nothing here is a pass or a no-value call: no prop was priced "
            "because none is approved, and enabling one is a reviewed "
            "decision behind the policy gate."
        )
        return summary

    if not staging.is_file():
        summary["status"] = NO_STAGING_STATUS
        summary["note"] = (
            "Prop markets are approved but no props staging file exists for "
            "this run. No price was invented; run the props staging fetch."
        )
        return summary

    frame = pd.read_csv(staging, dtype=str)
    required_columns = {
        "date",
        "home_team",
        "away_team",
        "market",
        "player",
        "selection",
        "american_odds",
        "book",
    }
    missing = required_columns - set(frame.columns)
    if missing:
        summary["status"] = NO_STAGING_STATUS
        summary["note"] = (
            f"The props staging file is missing columns {sorted(missing)}; "
            "refusing to price from a partial schema."
        )
        return summary
    frame["american_odds"] = pd.to_numeric(
        frame["american_odds"], errors="coerce"
    )
    frame = frame.dropna(subset=["american_odds"])
    frame = frame[frame["market"].isin(approved)]
    frame = frame[frame["date"] >= today]
    summary["markets_with_staged_prices"] = sorted(set(frame["market"]))

    if not logs_file.is_file():
        summary["status"] = NO_STAGING_STATUS
        summary["note"] = (
            "Prop markets are approved but the player match logs are "
            "missing, so no rate can be modelled and no pick is made."
        )
        return summary
    logs = pd.read_csv(logs_file, dtype=str)
    for stat in set(SETTLEMENT_COLUMNS.values()) | {"minutes"}:
        logs[stat] = pd.to_numeric(logs[stat], errors="coerce").fillna(0)
    model = PlayerPropsModel().fit(logs)

    # Best price per outcome across books, matching the card's behaviour.
    best: dict[tuple, dict] = {}
    for _, row in frame.iterrows():
        key = (
            row["date"],
            row["home_team"],
            row["away_team"],
            row["market"],
            row["player"],
            row["selection"],
        )
        if key not in best or float(row["american_odds"]) > float(
            best[key]["american_odds"]
        ):
            best[key] = row.to_dict()

    picks: list[PropPick] = []
    for row in best.values():
        market = str(row["market"])
        stat = SETTLEMENT_COLUMNS.get(market)
        if stat is None:
            continue
        # The player prices as a member of one of the two squads; venue
        # follows the team the logs last saw them with.
        rates = model.players.get(str(row["player"]))
        if rates is None:
            continue
        if rates.team == str(row["home_team"]):
            venue, opponent = "home", str(row["away_team"])
        elif rates.team == str(row["away_team"]):
            venue, opponent = "away", str(row["home_team"])
        else:
            # The logs know this player under another team: a transfer the
            # data has not caught up with. No opinion is the honest answer.
            continue
        name, point = _parse_selection(str(row["selection"]))
        if name.casefold() == "over" and point is not None:
            raw = model.over_probability(
                str(row["player"]), stat, point, opponent=opponent, venue=venue
            )
        elif market == "player_goal_scorer_anytime" and name.casefold() == "yes":
            raw = model.anytime_scorer_probability(
                str(row["player"]), opponent=opponent, venue=venue
            )
        else:
            raw = None
        if raw is None:
            continue
        probability = correction.apply(raw)
        american = float(row["american_odds"])
        implied = _implied_probability(american)
        edge = probability - implied
        if edge < edge_threshold:
            continue
        picks.append(
            PropPick(
                date=str(row["date"]),
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                market=market,
                player=str(row["player"]),
                selection=str(row["selection"]),
                model_probability=round(probability, 4),
                implied_probability=round(implied, 4),
                edge=round(edge, 4),
                american_odds=american,
                book=str(row["book"]),
                units=PROPS_UNITS,
            )
        )

    picks.sort(key=lambda p: -p.edge)
    summary["status"] = READY_STATUS
    summary["picks"] = [p.__dict__ for p in picks]
    summary["note"] = (
        "The standing measurement demonstrates no edge in these markets; "
        "these picks clear a deliberately high bar and carry the smallest "
        "stake the card uses. Books reprice on the team sheet after this "
        "card is built."
    )
    return summary


def save_player_props_card(
    output_dir: Path | None = None, **kwargs: object
) -> dict[str, object]:
    outputs = Path(output_dir) if output_dir else Path(OUTPUTS_DIR)
    outputs.mkdir(parents=True, exist_ok=True)
    summary = build_player_props_card(**kwargs)  # type: ignore[arg-type]

    json_path = outputs / CARD_JSON_FILENAME
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# Player Props Card",
        "",
        f"- Status: **{summary['status']}**",
        f"- Approved prop markets: "
        f"{', '.join(summary['approved_prop_markets']) or 'none'}",
        f"- Held prop markets: "
        f"{', '.join(summary['held_prop_markets']) or 'none'}",
        "",
        str(summary.get("note", "")),
        "",
    ]
    picks = summary.get("picks") or []
    if picks:
        lines += [
            "## Picks",
            "",
            "| Match | Market | Player | Selection | Model prob | Edge | "
            "Price | Book | Units |",
            "|:------|:-------|:-------|:----------|-----------:|-----:|"
            "------:|:-----|------:|",
        ]
        for pick in picks:
            lines.append(
                f"| {pick['home_team']} v {pick['away_team']} | "
                f"`{pick['market']}` | {pick['player']} | "
                f"{pick['selection']} | {pick['model_probability']:.1%} | "
                f"{pick['edge']:+.1%} | {pick['american_odds']:+.0f} | "
                f"{pick['book']} | {pick['units']} |"
            )
        lines.append("")
    lines += [
        "## Safety",
        "",
        "- No price fabricated, no bet placed, no settlement applied, no "
        "protected file written.",
        "",
    ]
    markdown_path = outputs / CARD_MARKDOWN_FILENAME
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "summary": summary,
        "json": str(json_path),
        "markdown": str(markdown_path),
    }
