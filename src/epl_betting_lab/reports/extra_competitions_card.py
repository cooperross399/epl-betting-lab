"""Selections for the competitions beyond the Premier League.

Cooper asked for EFL Cup and Champions League plays after being shown the
measurements, so this exists and is wired. What follows is what it is, recorded
where it cannot be mistaken for a recommendation to bet more of it.

**Both competitions can now be priced, for different reasons.**

Every EFL Cup club is English and has played in E0-E3, so the unified English
pool rates all of them. Champions League clubs are rated on the European pool,
where 701 European ties bridge eleven domestic leagues onto one scale — a scale
that beats a naive league-average prior by 8.5% on held-out ties, interval
-0.161 to -0.092.

**Neither has been shown to beat a price, and one has been shown not to.**

The EFL Cup rests on carrying a club's rating across a division boundary, and
that was measured: it is *worse* than calling the club average for its new
division (+0.0183 RMSE, interval +0.0046 to +0.0338 over 100 changes). What
transfers is the division, not the club — and a market that knows both clubs'
divisions knows that too, with the vig on its side.

The Champions League scale does carry club information out of sample. That is
category (a), predicting goals. It is not category (b), beating a price: the
Premier League model predicts goals respectably and carries beta = -0.023
against the closing line. Whether these ratings beat a Champions League price
needs the closing-line record the price collection is accumulating.

**The European scale overrates weak-league clubs, and those are exactly the
clubs it will find value on.** Fitted on everything, PSV Eindhoven comes out
second by attack, with Sporting, Benfica, Fenerbahce, Galatasaray and Celtic
above Real Madrid and Manchester City. A club that dominates a weak domestic
league scores heavily against weak opposition and 701 ties correct that only
partly. A selection on one of those clubs should be read with that in mind.

**Prices come from the observation feed, not the staging bundle.** The provider
policy's acceptance receipt is keyed on the provider rather than the competition
and its evidence only ever examined Premier League coverage. Routing these
through `data/staging/` would put them under an approval that never looked at
them. Reading from `price_feed_extra.csv` leaves the receipt untouched and
unsigned.

**Every row carries its competition**, so the out-of-sample ledger can tell
these apart from the Premier League card's. Mixing them would make both
uninterpretable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from epl_betting_lab.config import MAX_DEFAULT_JUICE, PROCESSED_DIR
from epl_betting_lab.data.european_clubs import provider_name
from epl_betting_lab.models.european_ratings import (
    EUROPEAN_RATINGS,
    build_european_pool,
)
from epl_betting_lab.models.poisson_goals import PoissonGoalsModel, UnratedTeam
from epl_betting_lab.models.unified_ratings import UNIFIED_RATINGS, build_pool
from epl_betting_lab.strategies.btts import evaluate_btts
from epl_betting_lab.strategies.count_markets import (
    COUNT_MARKETS,
    evaluate_count_market,
    fit_count_models,
)
from epl_betting_lab.strategies.derived_result import (
    evaluate_double_chance,
    evaluate_draw_no_bet,
)
from epl_betting_lab.strategies.totals import evaluate_total_25_anchored

DEFAULT_FEED = PROCESSED_DIR / "price_feed_extra.csv"

#: A tenth of a unit, the card's smallest. Sized to the evidence behind these
#: prices rather than to the edge the model claims for them.
EXTRA_UNITS = 0.1

#: `1x2` is left out for the same reason it is left out of the Premier League
#: card: it loses out of sample. Every other market the provider returns for a
#: competition is evaluated, and a market with no price simply produces no rows.
EXCLUDED_MARKETS = ("1x2",)

#: How many selections a competition may contribute. The Premier League card
#: caps at 8 for a rule with a measured record; these have none, so they get
#: fewer. A cap also stops a competition with many fixtures crowding the card.
MAX_EXTRA_BETS = 4


@dataclass(frozen=True)
class CompetitionSpec:
    key: str
    name: str
    #: Which rating pool can see this competition's clubs. The English pool
    #: cannot rate Real Madrid; the European pool cannot rate Grimsby.
    pool: str
    note: str


COMPETITIONS: dict[str, CompetitionSpec] = {
    "EFLC": CompetitionSpec(
        key="EFLC",
        name="EFL Cup (Carabao)",
        pool="english",
        note=(
            "Priced on the unified English ratings. Measured out of sample, a "
            "club's rating does **not** survive a division change — carrying it "
            "across is worse than calling the club average for its new division. "
            "What transfers is the division, which the market also knows."
        ),
    ),
    "UCL": CompetitionSpec(
        key="UCL",
        name="UEFA Champions League",
        pool="european",
        note=(
            "Priced on the European ratings, where 701 European ties bridge "
            "eleven leagues onto one scale — 8.5% better than a league-average "
            "prior on held-out ties. That scale **overrates clubs who dominate "
            "weak leagues**, and those are the clubs it will most often call "
            "value."
        ),
    ),
    "UEL": CompetitionSpec(
        key="UEL",
        name="UEFA Europa League",
        pool="european",
        note=(
            "Same European ratings as the Champions League, and **thinner in "
            "both directions**: more clubs come from countries with no domestic "
            "feed, so more fixtures are declined, and the ones that are priced "
            "rest on a scale calibrated mostly by Champions League ties."
        ),
    ),
    "UECL": CompetitionSpec(
        key="UECL",
        name="UEFA Europa Conference League",
        pool="european",
        note=(
            "The thinnest of the three. Only 24 Conference League ties survive "
            "club resolution across five seasons, against 701 for the Champions "
            "League, so this competition contributes almost nothing to the scale "
            "it is priced on and most of its fixtures involve a club the pool "
            "cannot rate at all."
        ),
    ),
}


@dataclass
class ExtraCard:
    selections: pd.DataFrame
    notes: list[str] = field(default_factory=list)
    priced: int = 0
    unrated: list[str] = field(default_factory=list)


def latest_prices(feed: pd.DataFrame, competition: str) -> pd.DataFrame:
    """Best price per selection at the most recent observation.

    The feed is append-only and holds every snapshot, so a fixture appears many
    times. Newest observation per selection, then the longest price across books
    at that moment — which is the price the card would be read against.
    """
    columns = ["home_team", "away_team", "market", "selection", "american_odds", "book"]
    if feed.empty or "competition" not in feed.columns:
        return pd.DataFrame(columns=columns)
    rows = feed[feed["competition"] == competition].copy()
    if rows.empty:
        return pd.DataFrame(columns=columns)
    # The provider names clubs its own way — "Paris Saint Germain" where
    # Football-Data says "Paris SG". Without this, a fixture is declined as
    # unrateable while both its clubs sit in the pool.
    rows["home_team"] = rows["home_team"].map(provider_name)
    rows["away_team"] = rows["away_team"].map(provider_name)
    rows["observed"] = pd.to_datetime(rows["observed_at"], errors="coerce", utc=True)
    rows["american_odds"] = pd.to_numeric(rows["american_odds"], errors="coerce")
    rows = rows.dropna(subset=["observed", "american_odds"])
    if rows.empty:
        return pd.DataFrame(columns=columns)
    keys = ["home_team", "away_team", "market", "selection"]
    newest = rows.groupby(keys)["observed"].transform("max")
    at_close = rows[rows["observed"] == newest]
    best = at_close.sort_values("american_odds", ascending=False).groupby(keys).head(1)
    return best[columns].reset_index(drop=True)


def _pool_for(spec: CompetitionSpec):
    if spec.pool == "english":
        matches = build_pool()
        return matches, UNIFIED_RATINGS
    pool = build_european_pool()
    return pool.matches, EUROPEAN_RATINGS


def build_extra_card(
    feed: pd.DataFrame,
    competition: str,
    *,
    min_edge: float = 0.035,
) -> ExtraCard:
    """Score one competition's fixtures against the prices on file."""
    spec = COMPETITIONS[competition]
    prices = latest_prices(feed, competition)
    if prices.empty:
        return ExtraCard(pd.DataFrame(), [f"No {spec.name} price on file."])

    matches, config = _pool_for(spec)
    model = PoissonGoalsModel().fit(matches, config=config)

    notes: list[str] = []
    records: list[dict[str, object]] = []
    unrated: list[str] = []
    for _, fixture in prices[["home_team", "away_team"]].drop_duplicates().iterrows():
        home, away = fixture["home_team"], fixture["away_team"]
        try:
            # allow_unrated stays off. A club the pool has never seen is refused,
            # not priced as an average side — the fault that made a League Two
            # club a 27% shot against Liverpool before the refusal existed.
            records.append(model.match_probabilities(home, away))
        except UnratedTeam:
            unrated.append(f"{home} v {away}")
    if unrated:
        notes.append(
            f"{len(unrated)} fixture(s) left out because a club has no rating in "
            f"the pool: {', '.join(sorted(unrated))}."
        )
    if not records:
        return ExtraCard(pd.DataFrame(), notes + [f"No {spec.name} fixture could be priced."])

    projections = pd.DataFrame(records)
    frames = [
        evaluate_btts(projections, prices, min_edge=min_edge, max_juice=MAX_DEFAULT_JUICE),
        evaluate_total_25_anchored(projections, prices, max_juice=MAX_DEFAULT_JUICE),
        evaluate_double_chance(projections, prices, min_edge=min_edge, max_juice=MAX_DEFAULT_JUICE),
        evaluate_draw_no_bet(projections, prices, min_edge=min_edge, max_juice=MAX_DEFAULT_JUICE),
    ]
    # Corners need their own fit, on columns that ship in the same files as the
    # scorelines and are fully populated in every European league. A pool
    # without them yields no models and therefore no rows, rather than an error.
    count_models = fit_count_models(matches)
    if count_models:
        for market in COUNT_MARKETS:
            frames.append(
                evaluate_count_market(
                    market, count_models, projections, prices,
                    min_edge=min_edge, max_juice=MAX_DEFAULT_JUICE,
                )
            )
    else:
        notes.append("No corner model: the pool carries no corner counts.")

    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return ExtraCard(pd.DataFrame(), notes + ["No selection cleared the rules."], priced=len(records))

    selections = pd.concat(frames, ignore_index=True)
    selections = selections[~selections["market"].isin(EXCLUDED_MARKETS)].copy()
    if selections.empty:
        return ExtraCard(pd.DataFrame(), notes + ["No selection cleared the rules."], priced=len(records))

    # Only what the rules actually pass. Without this every evaluated row is
    # printed, negative edges included: the first run of this module offered a
    # -39.5% draw-no-bet as a selection. The Premier League card filters on the
    # same status and for the same reason.
    before = len(selections)
    selections = selections[selections["status"] == "BETTABLE"].copy()
    if selections.empty:
        return ExtraCard(
            pd.DataFrame(),
            notes + [f"None of {before} priced selections cleared the rules."],
            priced=len(records),
        )
    edge = selections.get("calibrated_edge", selections.get("raw_edge"))
    selections = selections.assign(_edge=pd.to_numeric(edge, errors="coerce"))
    selections = selections.sort_values("_edge", ascending=False).head(MAX_EXTRA_BETS)
    selections = selections.drop(columns=["_edge"])
    selections["competition"] = competition
    selections["suggested_units"] = EXTRA_UNITS
    return ExtraCard(selections, notes, priced=len(records), unrated=unrated)


def render_extra_card(cards: dict[str, ExtraCard]) -> list[str]:
    """Markdown for the competitions beyond the Premier League."""
    lines: list[str] = ["## Beyond the Premier League", ""]
    lines += [
        "Neither competition below has been shown to beat a price, and the EFL "
        "Cup has been shown not to. They are staked at "
        f"{EXTRA_UNITS} units for that reason. See "
        "`data/outputs/unified_ratings.md` and `data/outputs/european_ratings.md`.",
        "",
    ]
    for key, card in cards.items():
        spec = COMPETITIONS[key]
        lines += [f"### {spec.name}", "", spec.note, ""]
        if card.selections.empty:
            lines += ["_No selection this run._", ""]
            lines += [f"- {note}" for note in card.notes] + [""]
            continue
        lines += [
            "| Match | Market | Selection | Edge | Price | Book | Units |",
            "|:--|:--|:--|--:|--:|:--|--:|",
        ]
        for _, row in card.selections.iterrows():
            edge = row.get("calibrated_edge", row.get("raw_edge"))
            edge_text = f"{float(edge) * 100:+.1f}%" if pd.notna(edge) else "—"
            lines.append(
                f"| {row['home_team']} v {row['away_team']} | `{row['market']}` | "
                f"{row['selection']} | {edge_text} | {int(row['american_odds']):+d} | "
                f"{row.get('book', '')} | {row['suggested_units']} |"
            )
        lines.append("")
        lines += [f"- {note}" for note in card.notes] + [""]
    return lines
