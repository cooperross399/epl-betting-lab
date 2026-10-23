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

from epl_betting_lab.books import bettable_only
from epl_betting_lab.staging_provider_policy import entry_is_complete_approval
from epl_betting_lab.config import (
    PROPS_CARD_JSON,
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
    STAGING_DIR,
)
from epl_betting_lab.models.player_props import (
    FPL_STATS,
    PlayerPropsModel,
    PlayerRates,
    PropCalibration,
    add_card_columns,
)
from epl_betting_lab.providers.fpl_players import (
    FPL_LOGS_FILENAME,
    FPL_PRIOR_FILENAME,
)
from epl_betting_lab.providers.player_props_staging import (
    PROP_EVENT_MARKETS,
    PROPS_STAGING_FILENAME,
)
from epl_betting_lab.reports.player_props_backtest import (
    SETTLEMENT_COLUMNS,
    YES_MARKETS,
    _implied_probability,
    _parse_selection,
    _player_key,
)


CARD_JSON_FILENAME = PROPS_CARD_JSON
CARD_MARKDOWN_FILENAME = "player_props_card.md"

HELD_STATUS = "Held by policy"
READY_STATUS = "Props card ready"
NO_STAGING_STATUS = "No props staging evidence"

#: The correction proven on held-out data (PR #237). Refit by rerunning the
#: measurement with a split; never hand-tune.
SHIPPED_CORRECTION = PropCalibration(
    intercept=-0.2383, slope=0.9133, fitted_on=7254
)

#: Markets the shipped correction does not touch. It was fitted on shots,
#: shots on target, assists and the anytime scorer only; applying it to
#: cards, tackles or saves would borrow a measurement from markets they are
#: not, so their probabilities are the model's own, uncorrected.
UNCORRECTED_MARKETS = frozenset(
    {
        "player_to_receive_card",
        "player_to_receive_red_card",
        "player_tackles_alternate",
        "player_goalie_saves",
        "player_goalie_saves_alternate",
    }
)

#: Above every match-level bar, for the team-sheet deficit.
PROPS_EDGE_THRESHOLD = 0.08

#: The smallest stake the card uses anywhere. Props have no demonstrated
#: edge; a larger number would imply one.
PROPS_UNITS = 0.1


@dataclass(frozen=True)
class PropPick:
    date: str
    #: The provider's exact kick-off timestamp, carried from the staging
    #: file. It was written there by `player_props_staging` and dropped
    #: here, so the only staleness filter this section had was the
    #: date-string compare `frame["date"] >= today` — under which a fixture
    #: that kicked off at 12:30 is still offered by the 15:00 run, because
    #: "2026-10-03" >= "2026-10-03". That is the defect that shipped eight
    #: already-played fixtures on 2026-09-28, for the one section that got
    #: neither the kickoff gate nor the freshness audit.
    #:
    #: Empty when the staging file predates this column: recorded as unknown
    #: rather than guessed, which `card_freshness` counts as unchecked.
    kickoff_time: str
    home_team: str
    away_team: str
    market: str
    player: str
    #: The player's side, from the model's own rates (the staging row has
    #: home and away but never says which the player is on).
    team: str
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
        # The same envelope the match card reads: a market list under a
        # `proposed` or `revoked` entry, or one with no reviewer or receipt,
        # approves nothing here either.
        if not entry_is_complete_approval(entry):
            continue
        markets = entry.get("required_markets")
        if isinstance(markets, list):
            approved.update(str(item).strip() for item in markets)
    return [m for m in PROP_EVENT_MARKETS if m in approved]


def drop_started_fixtures(frame: pd.DataFrame, moment: datetime) -> pd.DataFrame:
    """Rows whose kick-off has not passed, by the provider's own timestamp.

    The only staleness filter this section had was the date-string compare
    `frame["date"] >= today`, which keeps a fixture on the card for the whole
    day it is played: `"2026-10-03" >= "2026-10-03"` is true at 15:00 for a
    match that kicked off at 12:30. `player_props_staging` has been writing
    `commence_time` into every row the whole time and nothing read it.

    A separate function so it can be tested on its own. Reaching this filter
    through `build_player_props_card` needs an approved policy, a staging
    file and player match logs, and a test that has to build all three to
    check a comparison is a test that will be deleted.

    An unparseable or missing timestamp is KEPT. The date compare still
    applies to it and `card_freshness` will count it unchecked, which is the
    honest answer; dropping a fixture because a column would not parse is the
    worse failure.
    """
    if "commence_time" not in frame.columns:
        return frame
    kickoff = pd.to_datetime(frame["commence_time"], errors="coerce", utc=True)
    cutoff = pd.Timestamp(moment)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    return frame[~(kickoff <= cutoff)]


#: Markets whose pick is a goalkeeper. Cooper, 2026-10-23: "for goalie saves
#: just put the team name. Idk goalies names".
GOALKEEPER_MARKETS = frozenset({"player_goalie_saves", "player_goalie_saves_alternate"})


def display_player(pick: Mapping[str, object]) -> str:
    """The name a reader sees: "Brighton goalkeeper" for a saves pick, the
    player otherwise. The pick's `player` field is untouched, because
    settlement matches on it. With no team recorded the name stays."""
    team = str(pick.get("team") or "").strip()
    if str(pick.get("market")) in GOALKEEPER_MARKETS and team:
        return f"{team} goalkeeper"
    return str(pick.get("player") or "")


def needs_fpl_logs(markets: list[str]) -> bool:
    """Whether any of `markets` is rated on the Fantasy Premier League logs."""
    return any(SETTLEMENT_COLUMNS.get(m) in FPL_STATS for m in markets)


def _resolve_player(
    model: PlayerPropsModel, name: str, home: str, away: str
) -> PlayerRates | None:
    """The model's player for a book's spelling, on one of the two sides.

    The exact name first. Otherwise a name whose tokens contain, or are
    contained by, exactly one squad player's tokens on either side — books
    add or drop given names ("Iyenoma Destiny Udogie" against FPL's "Destiny
    Udogie"). Any ambiguity is no opinion, never a guess.
    """
    exact = model.players.get(name)
    if exact is not None:
        return exact
    tokens = frozenset(_player_key(name).split())
    if not tokens:
        return None
    found = [
        rates
        for rates in model.players.values()
        if rates.team in (home, away)
        and (
            (player_tokens := frozenset(_player_key(rates.player).split()))
            and (player_tokens <= tokens or tokens <= player_tokens)
        )
    ]
    return found[0] if len(found) == 1 else None


def _one_stake_per_outcome(picks: list[PropPick]) -> list[PropPick]:
    """Keep the best-edge rung of each player's outcome.

    A ladder (`Over@0.5`, `Over@1.5`, ...) and two markets on one stat (the
    saves line and the saves ladder) settle on one number: staking every
    rung that clears the bar is one position sized several times. Grouped on
    fixture, player, stat and side; the line is what is chosen between.
    """
    best: dict[tuple, PropPick] = {}
    for pick in picks:
        side, _ = _parse_selection(pick.selection)
        key = (
            pick.date,
            pick.home_team,
            pick.away_team,
            SETTLEMENT_COLUMNS.get(pick.market, pick.market),
            pick.player,
            "over" if side.casefold() == "yes" else side.casefold(),
        )
        if key not in best or pick.edge > best[key].edge:
            best[key] = pick
    return list(best.values())


def build_player_props_card(
    *,
    props_staging_path: Path | None = None,
    logs_path: Path | None = None,
    fpl_logs_path: Path | None = None,
    fpl_prior_path: Path | None = None,
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
    fpl_logs_file = (
        Path(fpl_logs_path)
        if fpl_logs_path
        else Path(PROCESSED_DIR) / FPL_LOGS_FILENAME
    )
    fpl_prior_file = (
        Path(fpl_prior_path)
        if fpl_prior_path
        else Path(fpl_logs_file).parent / FPL_PRIOR_FILENAME
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
    # Only a price Cooper can take, and before the staged-market evidence is
    # read: a market priced only at ReBet or Courtside is not on offer to him.
    frame = bettable_only(frame)
    frame = frame[frame["date"] >= today]
    frame = drop_started_fixtures(frame, moment)
    # Every prop market holding a live price, approved or not: a held
    # market's prices are the evidence its approval binds to.
    summary["markets_with_staged_prices"] = sorted(
        set(frame["market"]) & set(PROP_EVENT_MARKETS)
    )
    frame = frame[frame["market"].isin(approved)]

    if not logs_file.is_file():
        summary["status"] = NO_STAGING_STATUS
        summary["note"] = (
            "Prop markets are approved but the player match logs are "
            "missing, so no rate can be modelled and no pick is made."
        )
        return summary
    logs = add_card_columns(pd.read_csv(logs_file, dtype=str))
    for stat in set(SETTLEMENT_COLUMNS.values()) | {"minutes"}:
        if stat in logs.columns:
            logs[stat] = pd.to_numeric(logs[stat], errors="coerce").fillna(0)
    model = PlayerPropsModel().fit(logs)

    # Tackles and saves are rated on the Fantasy Premier League logs. Absent
    # logs mean no opinion on those markets, never a baseline one.
    fpl_model: PlayerPropsModel | None = None
    if needs_fpl_logs(approved) and fpl_logs_file.is_file():
        fpl_logs = pd.read_csv(fpl_logs_file, dtype=str)
        if not fpl_logs.empty:
            for column in ("minutes", *FPL_STATS):
                fpl_logs[column] = pd.to_numeric(
                    fpl_logs[column], errors="coerce"
                ).fillna(0)
            prior = (
                pd.read_csv(fpl_prior_file, dtype=str)
                if fpl_prior_file.is_file()
                else None
            )
            fpl_model = PlayerPropsModel(stats=FPL_STATS).fit(
                fpl_logs, prior=prior
            )

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
        source = fpl_model if stat in FPL_STATS else model
        if source is None:
            continue
        # The player prices as a member of one of the two squads; venue
        # follows the team the logs last saw them with.
        rates = _resolve_player(
            source, str(row["player"]), str(row["home_team"]), str(row["away_team"])
        )
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
            raw = source.over_probability(
                rates.player, stat, point, opponent=opponent, venue=venue
            )
        elif market in YES_MARKETS and name.casefold() == "yes":
            raw = source.over_probability(
                rates.player, stat, 0.5, opponent=opponent, venue=venue
            )
        else:
            raw = None
        if raw is None:
            continue
        probability = (
            raw if market in UNCORRECTED_MARKETS else correction.apply(raw)
        )
        american = float(row["american_odds"])
        implied = _implied_probability(american)
        edge = probability - implied
        if edge < edge_threshold:
            continue
        picks.append(
            PropPick(
                date=str(row["date"]),
                kickoff_time=str(row.get("commence_time") or "").strip(),
                home_team=str(row["home_team"]),
                away_team=str(row["away_team"]),
                market=market,
                player=str(row["player"]),
                team=rates.team,
                selection=str(row["selection"]),
                model_probability=round(probability, 4),
                implied_probability=round(implied, 4),
                edge=round(edge, 4),
                american_odds=american,
                book=str(row["book"]),
                units=PROPS_UNITS,
            )
        )

    picks = _one_stake_per_outcome(picks)
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

    markdown_path = outputs / CARD_MARKDOWN_FILENAME
    markdown_path.write_text(render_player_props_markdown(summary), encoding="utf-8")

    return {
        "summary": summary,
        "json": str(json_path),
        "markdown": str(markdown_path),
    }


def render_player_props_markdown(summary: Mapping[str, object]) -> str:
    """The props card as markdown."""
    lines = [
        "# Player Props Card",
        "",
        f"- Status: **{summary['status']}**",
        f"- Approved prop markets: "
        f"{', '.join(summary.get('approved_prop_markets') or []) or 'none'}",
        f"- Held prop markets: "
        f"{', '.join(summary.get('held_prop_markets') or []) or 'none'}",
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
                f"`{pick['market']}` | {display_player(pick)} | "
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
    return "\n".join(lines)
