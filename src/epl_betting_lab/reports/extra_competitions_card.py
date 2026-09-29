"""Selections for the competitions beyond the Premier League.

Cooper asked for EFL Cup and Champions League plays after being shown the
measurements, so this exists and is wired. What follows is what it is, recorded
where it cannot be mistaken for a recommendation to bet more of it.

**Both competitions can now be priced, for different reasons.**

Every EFL Cup club is English and has played in E0-E3, so the unified English
pool rates all of them. Champions League clubs are rated on the European pool,
where 868 European ties bridge eleven domestic leagues onto one scale — a scale
that beats a naive league-average prior by 7.45% on held-out ties, interval
-0.1387 to -0.0798.

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
league scores heavily against weak opposition and 868 ties correct that only
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

import json
from datetime import datetime, timezone
from pathlib import Path

from dataclasses import dataclass, field

import pandas as pd

from epl_betting_lab.books import bettable_only, is_bettable
from epl_betting_lab.config import EXTRA_CARD_JSON, MAX_DEFAULT_JUICE, OUTPUTS_DIR, PROCESSED_DIR
from epl_betting_lab.data.european_clubs import provider_name
from epl_betting_lab.data.international_teams import archive_name
from epl_betting_lab.models.international_ratings import (
    MIN_MATCHES,
    INTERNATIONAL_RATINGS,
    build_international_pool,
    fit_international_model,
)
from epl_betting_lab.models.european_ratings import (
    BRIDGE_IMPROVEMENT_PCT,
    BRIDGE_TIES,
    CHAMPIONS_LEAGUE_TIES,
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


#: Markets a pool may not bet, beyond the card-wide exclusions.
#:
#: The international pool does not bet the goals LEVEL. Measured against the
#: de-vigged market on 45 live Nations League fixtures, the model put P(over
#: 2.5) at 0.418 where the market said 0.499 — 8 points low, the same direction
#: on every fixture, so every "under" and every "BTTS no" it produced was that
#: gap rather than anything about the fixture. Three of the first four
#: selections it ever made were low-scoring bets.
#:
#: A competition-specific baseline did not fix it and is not meant to: it fixes
#: the strength DIFFERENCE, closing the draw-no-bet gap from +0.051 to +0.021.
#: On the level it moves the wrong way, because this competition's own mean
#: total (2.53) is below the pool's (2.72) while the market prices above both
#: at about 2.69. Three defensible baselines span 0.36 goals, the market sits
#: outside all of them, and no free archive carries international prices — so
#: nothing can adjudicate it. The honest response is to bet the markets the
#: model can price and not the ones it cannot.
POOL_EXCLUDED_MARKETS: dict[str, frozenset[str]] = {
    "international": frozenset({"total_2_5", "btts"}),
}


@dataclass(frozen=True)
class CompetitionSpec:
    key: str
    name: str
    #: Which rating pool can see this competition's clubs. The English pool
    #: cannot rate Real Madrid; the European pool cannot rate Grimsby.
    pool: str
    note: str


COMPETITIONS: dict[str, CompetitionSpec] = {
    "UNL": CompetitionSpec(
        key="UNL",
        name="UEFA Nations League",
        pool="international",
        note=(
            "National teams, on a pool that shares no information with the club "
            "ratings — a country has never played any club in them, so nothing "
            "bridges the two and this is a second model. It **cannot be "
            "backtested**: no free archive carries international prices, so it "
            "can only be judged forward, at roughly 80 matches a year. "
            "**Only the result markets are bet here.** Measured against the "
            "de-vigged market across 45 live fixtures, the model put the chance "
            "of over 2.5 goals at 0.418 where the market said 0.499 — eight "
            "points low, the same way on every fixture — so `total_2_5` and "
            "`btts` are priced by a standing gap rather than by the fixture, and "
            "are withheld. Three of the first four selections this section ever "
            "made were low-scoring bets off that gap. The baselines are now "
            "this competition's own rather than the pool's, which halved a "
            "separate bias: it was applying +0.656 goals of home advantage "
            "where the Nations League's own is +0.346. Two expected problems "
            "measured out **not** to apply — seeding keeps League A away from "
            "League D, so 0.3% of fixtures have a favourite above 90% and none "
            "above 95%, and a rating survives squad turnover (r = +0.82 across "
            "seven years). One remains and cannot be fixed from the feed: 5.2% "
            "of these matches are at neutral venues and the price feed does not "
            "say which, so those carry a home advantage one side does not have."),
    ),
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
            f"Priced on the European ratings, where {BRIDGE_TIES} European "
            "ties bridge eleven leagues onto one scale — "
            f"{BRIDGE_IMPROVEMENT_PCT}% better than a league-average prior on "
            "held-out ties. That scale **overrates clubs who dominate weak "
            "leagues**, and those are the clubs it will most often call value."
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
            "The thinnest of the three. Only 24 Conference League ties "
            "survive club resolution across five seasons, against "
            f"{CHAMPIONS_LEAGUE_TIES} for the Champions League — both resolved "
            "counts, and together with the Europa League's 143 they are the "
            f"{BRIDGE_TIES}-tie bridge. So this competition contributes almost "
            "nothing to the scale it is priced on, and most of its fixtures "
            "involve a club the pool cannot rate at all."
        ),
    ),
}


@dataclass
class ExtraCard:
    selections: pd.DataFrame
    notes: list[str] = field(default_factory=list)
    priced: int = 0
    unrated: list[str] = field(default_factory=list)
    #: What the freshness gate withheld. Carried on the card rather than logged,
    #: because a section that quietly dropped half its fixtures and one that was
    #: quoted half as many look identical to a reader.
    gate: "SlateGate | None" = None

    @property
    def fixtures(self) -> int:
        """Every fixture with a price, whether or not it could be rated."""
        return self.priced + len(self.unrated)

    @property
    def carded(self) -> bool:
        """Is there anything here to show?

        A competition appears on the card when it can price at least one
        fixture. Not a threshold anybody chose: a competition that can price
        nothing has nothing to say, and printing its heading above eighteen
        lines of declines every run teaches the reader to skip the section that
        also carries the ones that do.

        Stated as a condition rather than a list, so a competition cards itself
        the moment its coverage improves and stops when it stops — the
        Conference League needs domestic feeds for Cyprus, Lithuania, Gibraltar
        and Andorra before it can say anything, and nobody has to remember to
        check."""
        return self.priced > 0


def name_map_for(competition: str):
    """Which name map this competition's teams go through.

    Clubs and national teams have separate maps. One dictionary for both would
    be two vocabularies sharing a key space, which is how "home" came to mean
    the provider in one table and the results feed in another.

    Factored out because the choice was made in one place and needed in two.
    `latest_prices` renamed the teams and the kickoff lookup did not, so a
    fixture whose provider spelling differs from Football-Data's — "AS Roma"
    against "Roma", "Atletico Madrid" against "Ath Madrid",
    "Union Saint-Gilloise" against "St. Gilloise" — was recorded with no
    kickoff at all. Gating was never wrong, because that works on the feed's own
    names throughout; what was lost was the kickoff on the record, which is what
    the freshness audit reads. Three of twelve selections on the first run after
    the audit shipped, and the audit's `unchecked` count is what surfaced it.
    """
    return archive_name if COMPETITIONS[competition].pool == "international" else provider_name


def latest_prices(feed: pd.DataFrame, competition: str) -> pd.DataFrame:
    """Best BETTABLE price per selection at the most recent observation.

    The feed is append-only and holds every snapshot, so a fixture appears many
    times. Newest observation per selection, then the longest price across the
    books Cooper can actually bet at — which is the price the card would be
    read against.

    "Bettable" was missing from that sentence and from the code. The Premier
    League path filters twice (`automated_card_input._best_quote` and
    `bettable_only(staged)`); this one took the longest price on the board
    whoever was offering it, and printed that book in the card's Book column
    beside prices that could be taken. `books.py` says why that is worse than
    no recommendation: it looks like the others.

    It has not yet shipped a bad price — every book in the 148-row September
    sample is bettable — and two things make it a matter of when. The reason
    `unknown_books` exists at all is that a new US book appearing and being
    quietly ignored costs real value; and `scripts/collect_extra_competitions.py`
    takes `--regions`, so one run with `eu` would hand every selection to
    Pinnacle, which is always the longest price and is never bettable.
    """
    # `provider_event_id` travels with the price because it is the only
    # identity that survives renaming. The card maps the provider's club names
    # onto Football-Data's before pricing, so a later join from the record back
    # to the feed on names compares "Roma" against "AS Roma" and finds nothing
    # — which is exactly how the freshness audit came back `unchecked: 3`.
    columns = [
        "home_team", "away_team", "market", "selection", "american_odds",
        "book", "provider_event_id",
    ]
    if feed.empty or "competition" not in feed.columns:
        return pd.DataFrame(columns=columns)
    rows = feed[feed["competition"] == competition].copy()
    if rows.empty:
        return pd.DataFrame(columns=columns)
    # The provider names clubs its own way — "Paris Saint Germain" where
    # Football-Data says "Paris SG". Without this, a fixture is declined as
    # unrateable while both its clubs sit in the pool.
    rename = name_map_for(competition)
    rows["home_team"] = rows["home_team"].map(rename)
    rows["away_team"] = rows["away_team"].map(rename)
    if "provider_event_id" not in rows.columns:
        rows["provider_event_id"] = ""
    rows["observed"] = pd.to_datetime(rows["observed_at"], errors="coerce", utc=True)
    rows["american_odds"] = pd.to_numeric(rows["american_odds"], errors="coerce")
    rows = rows.dropna(subset=["observed", "american_odds"])
    if rows.empty:
        return pd.DataFrame(columns=columns)
    keys = ["home_team", "away_team", "market", "selection"]
    newest = rows.groupby(keys)["observed"].transform("max")
    at_close = rows[rows["observed"] == newest]
    # Before the sort, not after. Picking the longest price and then checking
    # whether it can be taken would discard the selection rather than fall
    # back to the best price that can.
    at_close = bettable_only(at_close)
    if at_close.empty:
        return pd.DataFrame(columns=columns)
    best = at_close.sort_values("american_odds", ascending=False).groupby(keys).head(1)
    return best[columns].reset_index(drop=True)


def unbettable_books(feed: pd.DataFrame, competition: str) -> list[str]:
    """Books quoting this competition that the card will not price at.

    Reported rather than dropped in silence. A book that appears here and
    ought to be bettable is a line missing from `books.BETTABLE_BOOKS`, which
    is Cooper's decision to make and not one a filter should make quietly.
    """
    if feed.empty or "competition" not in feed.columns or "book" not in feed.columns:
        return []
    rows = feed[feed["competition"] == competition]
    seen = {str(book) for book in rows["book"].dropna()}
    return sorted(book for book in seen if not is_bettable(book))


#: A fixture whose kickoff cannot be established from the feed. Same word the
#: Premier League card uses for the same state, because it is the same state:
#: `automated_card.KICKOFF_UNCONFIRMED_STATUS`.
KICKOFF_UNCONFIRMED = "kickoff unconfirmed"

#: How far apart two fixtures can be and still belong to the same round.
#:
#: Measured on the feed as it stood on 2026-09-28. WITHIN a round the widest
#: spread is 5 days (a Nations League window, 28 September to 2 October); the
#: EFL Cup's fourth round spans 3 days and a Champions League matchday 2.
#: BETWEEN rounds the narrowest gap is 28 days (Europa League matchday 1 on
#: 16-17 September, matchday 2 on 15 October); the EFL Cup's third and fourth
#: rounds are 41 days apart. Seven sits between the two with room on both
#: sides.
ROUND_GAP_DAYS = 7


@dataclass(frozen=True)
class SlateGate:
    """What survived the freshness gate, and what it cost.

    The counts are reported rather than kept internally. A section that quietly
    drops half its fixtures and one that was quoted half as many fixtures look
    identical on the card, and this project has been caught by that shape more
    than once.
    """

    kept: pd.DataFrame
    played: list[str] = field(default_factory=list)
    unconfirmed: list[str] = field(default_factory=list)
    held_back: list[str] = field(default_factory=list)
    rounds: int = 0

    @property
    def dropped(self) -> int:
        return len(self.played) + len(self.unconfirmed) + len(self.held_back)


def _fixture_kickoffs(rows: pd.DataFrame) -> dict[tuple[str, str], pd.Timestamp | None]:
    """(home, away) -> kickoff, or None where it cannot be established.

    `commence_time` is the provider's own timestamp and is preferred. Rows
    collected before it was carried have only `date`, a day with no clock, and
    a day cannot show that a fixture has not started yet — so a dated-only
    fixture resolves to the START of its day.

    That direction matters and the first version of this had it backwards.
    Stamping the END of the day makes a kickoff look later than it was, so a
    fixture that kicked off at 16:00 survived an 18:17 gate — admitting a
    finished game, which is the fault being fixed. Stamping the start withholds
    any same-day dated-only fixture instead. Withholding a fixture that was
    still to come costs one bet; admitting one that has finished is the bug.

    A pair quoted with two different kickoffs resolves to None, the same way
    the Premier League card treats a conflicting pair: an ambiguous identity is
    worse than none.
    """
    kickoffs: dict[tuple[str, str], pd.Timestamp | None] = {}
    seen_conflict: set[tuple[str, str]] = set()
    has_commence = "commence_time" in rows.columns
    for row in rows.itertuples():
        key = (str(row.home_team).strip().casefold(), str(row.away_team).strip().casefold())
        if key in seen_conflict:
            continue
        stamp = pd.NaT
        if has_commence:
            stamp = pd.to_datetime(getattr(row, "commence_time", None), errors="coerce", utc=True)
        if pd.isna(stamp):
            day = pd.to_datetime(getattr(row, "date", None), errors="coerce", utc=True)
            # Start of the fixture's day. Anything later flatters a stale
            # fixture into surviving the gate.
            stamp = day.normalize() if not pd.isna(day) else pd.NaT
        resolved = None if pd.isna(stamp) else stamp
        if key in kickoffs and kickoffs[key] != resolved:
            seen_conflict.add(key)
            kickoffs[key] = None
            continue
        kickoffs[key] = resolved
    return kickoffs


def gate_slate(rows: pd.DataFrame, *, now: pd.Timestamp) -> SlateGate:
    """Drop fixtures that have kicked off, and hold back a later round.

    The feed is append-only and nothing ever left it. `latest_prices` returns
    the newest OBSERVATION per fixture, which for a fixture that stopped being
    quoted is its last observation — so a fixture remained eligible to be
    priced for as long as the feed existed. On 2026-09-28 that put an EFL Cup
    third-round tie played on 16 September, a Europa League matchday-1 tie from
    the same date, and three Nations League fixtures from 25-27 September onto
    a card generated on the 28th.

    Two separate faults, and both are closed here. The first is staleness: a
    game that has kicked off is not a play. The second is that the pool spanned
    rounds — the EFL Cup feed held the third round and the fourth at once, which
    is why one club appeared in two fixtures — so only the earliest surviving
    round is priced and a later one is named rather than silently included.
    """
    columns = list(rows.columns)
    if rows.empty:
        return SlateGate(kept=pd.DataFrame(columns=columns))

    kickoffs = _fixture_kickoffs(rows)
    played: list[str] = []
    unconfirmed: list[str] = []
    keep: set[tuple[str, str]] = set()
    labels: dict[tuple[str, str], str] = {}
    for row in rows.itertuples():
        key = (str(row.home_team).strip().casefold(), str(row.away_team).strip().casefold())
        labels.setdefault(key, f"{row.home_team} v {row.away_team}")
    for key, kickoff in kickoffs.items():
        if kickoff is None:
            unconfirmed.append(labels[key])
        elif kickoff <= now:
            played.append(labels[key])
        else:
            keep.add(key)

    # One round. Distinct surviving days, split where the gap exceeds
    # ROUND_GAP_DAYS; the earliest group is the current or next round.
    days = sorted({kickoffs[key].normalize() for key in keep})
    rounds = 1 if days else 0
    cutoff = days[-1] if days else None
    if days:
        for earlier, later in zip(days, days[1:]):
            if (later - earlier).days > ROUND_GAP_DAYS:
                rounds += 1
                if cutoff == days[-1]:
                    cutoff = earlier
    held_back: list[str] = []
    if cutoff is not None and rounds > 1:
        for key in sorted(keep):
            if kickoffs[key].normalize() > cutoff:
                held_back.append(labels[key])
        keep = {key for key in keep if kickoffs[key].normalize() <= cutoff}

    mask = rows.apply(
        lambda row: (
            str(row["home_team"]).strip().casefold(),
            str(row["away_team"]).strip().casefold(),
        )
        in keep,
        axis=1,
    )
    return SlateGate(
        kept=rows[mask].copy(),
        played=sorted(played),
        unconfirmed=sorted(unconfirmed),
        held_back=sorted(held_back),
        rounds=rounds,
    )


def _pool_for(spec: CompetitionSpec):
    """Matches, rating config, and a baseline override where one is needed.

    The override exists because `PoissonGoalsModel` takes its two baselines
    from the mean of whatever frame it is fitted on. For a domestic league that
    is right: every row is one competition, played at a real venue. For the
    international pool it is neither — the frame mixes competitions whose home
    advantage ranges from +0.35 goals to +0.77, and mixes real-venue rows with
    neutral ones. Fitted on that frame the model priced every Nations League
    fixture with the pool's +0.656 when the competition's own is +0.346, and on
    the live feed called the home side 0.614 in draw-no-bet where the de-vigged
    market said 0.563.
    """
    if spec.pool == "international":
        # Priced as a home fixture, which is right for 94.8% of Nations League
        # matches and wrong for the rest. `InternationalModel.expected_goals`
        # can take the venue and refuses to guess it; the price feed simply
        # does not carry one, and the provider does not say. Rather than pass a
        # neutral flag this layer would have to invent, the card uses the same
        # home/away path as every other competition and the note says what that
        # costs. The pool's own baselines still come out of a venue-aware fit.
        pool = build_international_pool()
        fitted = fit_international_model(pool)
        # Priced as a real-venue fixture: the feed carries no venue and 94.8%
        # of Nations League matches are played at one. `expected_goals` refuses
        # to guess a venue; this layer has to choose one, and it says so on the
        # card rather than in a comment.
        baseline = fitted.competition_baselines.get((spec.key, False))
        # `rateable` travels with the baseline now. It was computed on the same
        # line and dropped: this function fitted the whole InternationalModel,
        # read one number out of it, and returned three values that did not
        # include the appearance floor. `InternationalModel.expected_goals` is
        # the only place MIN_MATCHES is enforced and it is called from nowhere
        # in src/ or scripts/, so the floor was a measurement with no effect.
        return pool.matches, INTERNATIONAL_RATINGS, baseline, fitted.rateable
    if spec.pool == "english":
        matches = build_pool()
        return matches, UNIFIED_RATINGS, None, None
    pool = build_european_pool()
    return pool.matches, EUROPEAN_RATINGS, None, None


#: How many fixture names a drop note prints before summarising. The first
#: version printed all of them and a Nations League run dropped 42, which is a
#: paragraph of names where a count was wanted. The count is always exact.
NAMED_IN_A_NOTE = 6


def _some(names: list[str]) -> str:
    """The first few names, then how many more."""
    if len(names) <= NAMED_IN_A_NOTE:
        return ", ".join(names)
    shown = ", ".join(names[:NAMED_IN_A_NOTE])
    return f"{shown}, and {len(names) - NAMED_IN_A_NOTE} more"


def _gate_notes(gate: SlateGate, spec: CompetitionSpec) -> list[str]:
    """What the gate withheld, in the card's own voice."""
    notes: list[str] = []
    if gate.played:
        notes.append(
            f"{len(gate.played)} fixture(s) dropped as already kicked off: "
            f"{_some(gate.played)}."
        )
    if gate.unconfirmed:
        notes.append(
            f"{len(gate.unconfirmed)} fixture(s) dropped because their kickoff "
            f"could not be confirmed from the feed: {_some(gate.unconfirmed)}."
        )
    if gate.held_back:
        notes.append(
            f"The {spec.name} pool spanned {gate.rounds} rounds. Only the "
            f"earliest is priced; {len(gate.held_back)} fixture(s) from a later "
            f"round were held back: {_some(gate.held_back)}."
        )
    return notes


def build_extra_card(
    feed: pd.DataFrame,
    competition: str,
    *,
    min_edge: float = 0.035,
    now: pd.Timestamp | None = None,
) -> ExtraCard:
    """Score one competition's fixtures against the prices on file.

    `now` is the card's generation time and defaults to the present. Every
    fixture whose kickoff is at or before it is dropped before anything is
    priced — see `gate_slate` for why that was needed.
    """
    spec = COMPETITIONS[competition]
    moment = pd.Timestamp.now("UTC") if now is None else pd.Timestamp(now)
    if moment.tzinfo is None:
        moment = moment.tz_localize("UTC")

    rows = feed[feed["competition"] == competition] if "competition" in feed.columns else feed.iloc[0:0]
    gate = gate_slate(rows, now=moment)
    prices = latest_prices(gate.kept, competition)
    gate_notes = _gate_notes(gate, spec)
    # Built here rather than after the early return below. A feed quoting
    # only books that cannot be bet leaves `prices` empty, which takes the
    # "No price on file" path — a sentence that is true about the filter and
    # false about the feed, and the note explaining the difference sat forty
    # lines further down where that path never reaches. The reader would see
    # a competition reported as unquoted when it was quoted all along.
    ignored = unbettable_books(gate.kept, competition)
    ignored_note = (
        [
            f"{len(ignored)} book(s) quoting this competition are not priced "
            f"against, because they are not on the bettable list: "
            f"{', '.join(ignored)}. If one of those should be bettable it is a "
            "line missing from `books.BETTABLE_BOOKS`, not a filter to loosen."
        ]
        if ignored
        else []
    )
    if prices.empty:
        quoted = not gate.kept.empty
        reason = (
            f"No bettable {spec.name} price on file: every quote on the feed "
            "is from a book that is not bet at."
            if quoted and ignored
            else f"No {spec.name} price on file."
        )
        return ExtraCard(
            pd.DataFrame(),
            gate_notes + [reason] + ignored_note,
            gate=gate,
        )

    matches, config, baseline, rateable = _pool_for(spec)
    model = PoissonGoalsModel().fit(matches, config=config)
    if baseline is not None:
        # Every market the card prices comes off the score matrix, which comes
        # off these two numbers, so correcting them corrects totals, BTTS,
        # double chance and draw-no-bet at once.
        model.avg_home_goals, model.avg_away_goals = baseline

    notes: list[str] = list(gate_notes) + ignored_note
    for market in sorted(POOL_EXCLUDED_MARKETS.get(spec.pool, ())):
        notes.append(
            f"`{market}` is not bet here: the model sits about 8 points below "
            "the market on the goals level for every fixture, so a selection in "
            "that market would be the gap rather than the fixture."
        )
    if spec.pool == "international":
        # The results archive behind this pool runs about a month behind, so by
        # a window's third matchday the fit has not seen the first two. Said out
        # loud because the alternative is a card that looks current: read on
        # 2026-09-23 the archive ended 2026-08-26 and held no September results
        # at all, including matches this card was pricing that day.
        latest = pd.to_datetime(matches["date"]).max()
        if pd.notna(latest):
            notes.append(
                f"Ratings include no result after {latest.date()}; the results "
                "archive runs about a month behind, so the current "
                "international window is not in the fit."
            )
    records: list[dict[str, object]] = []
    unrated: list[str] = []
    thin: list[str] = []
    for _, fixture in prices[["home_team", "away_team"]].drop_duplicates().iterrows():
        home, away = fixture["home_team"], fixture["away_team"]
        # The appearance floor, applied. `PoissonGoalsModel.fit` puts every
        # team in `matches` into `team_strengths` whatever its appearance
        # count, so its only guard is "absent from the pool" — a side with
        # three matches on file is rated off three matches and priced like any
        # other. MIN_MATCHES exists because under six appearances the model
        # loses 0.10 log-loss of skill against knowing nothing about the teams.
        #
        # Nothing changes today: all 55 UEFA Nations League sides clear twelve
        # and so do all 41 CONCACAF ones. It binds when a lightly-played
        # national team reaches a registered competition, or when an archive
        # spelling splits one side's history in two.
        if rateable is not None and (home not in rateable or away not in rateable):
            thin.append(f"{home} v {away}")
            continue
        try:
            # allow_unrated stays off. A club the pool has never seen is refused,
            # not priced as an average side — the fault that made a League Two
            # club a 27% shot against Liverpool before the refusal existed.
            records.append(model.match_probabilities(home, away))
        except UnratedTeam:
            unrated.append(f"{home} v {away}")
    if thin:
        notes.append(
            f"{len(thin)} fixture(s) left out because a side has fewer than "
            f"{MIN_MATCHES} matches in the pool, which is too few to rate: "
            f"{_some(sorted(thin))}."
        )
        # Counted with the refusals in the summary line, because both are
        # "priced nowhere" and a reader asking why the count is short wants
        # one number, not two vocabularies for the same outcome.
        unrated = unrated + thin
    if unrated:
        notes.append(
            f"{len(unrated)} fixture(s) left out because a club has no rating in "
            f"the pool: {', '.join(sorted(unrated))}."
        )
    if not records:
        # `unrated` travels with the early return. Without it the summary line
        # reads "0 of 0 fixtures rateable", which says the competition had no
        # fixtures rather than that none of its eighteen could be rated — a
        # quiet week and a coverage wall, told apart by the one number that
        # distinguishes them.
        return ExtraCard(
            pd.DataFrame(),
            notes + [f"No {spec.name} fixture could be priced."],
            priced=0,
            unrated=unrated,
            gate=gate,
        )

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
        # `unrated` travels with every return, not just the early one. It was
        # added to the coverage-wall return and missed on the three below, so a
        # competition where nothing cleared reported "N of N fixtures rateable"
        # while several had in fact been declined — the same "0 of 0" fault the
        # early return exists to prevent, surviving on the paths a quiet week
        # actually takes.
        return ExtraCard(
            pd.DataFrame(),
            notes + ["No selection cleared the rules."],
            priced=len(records),
            unrated=unrated,
            gate=gate,
        )

    selections = pd.concat(frames, ignore_index=True)
    barred = set(EXCLUDED_MARKETS) | set(POOL_EXCLUDED_MARKETS.get(spec.pool, ()))
    selections = selections[~selections["market"].isin(barred)].copy()
    if selections.empty:
        return ExtraCard(
            pd.DataFrame(),
            notes + ["No selection cleared the rules."],
            priced=len(records),
            unrated=unrated,
            gate=gate,
        )

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
            unrated=unrated,
            gate=gate,
        )
    edge = selections.get("calibrated_edge", selections.get("raw_edge"))
    selections = selections.assign(_edge=pd.to_numeric(edge, errors="coerce"))
    selections = selections.sort_values("_edge", ascending=False).head(MAX_EXTRA_BETS)
    selections = selections.drop(columns=["_edge"])
    selections["competition"] = competition
    selections["suggested_units"] = EXTRA_UNITS
    # Carried from the gate, which already resolved every fixture's kickoff.
    # Recomputing it here would be a second implementation of the same
    # question, and the two could disagree.
    # Keyed on the SAME names the selections carry. Built from the raw feed
    # names it missed every fixture the name map renames.
    renamed = gate.kept.copy()
    rename = name_map_for(competition)
    renamed["home_team"] = renamed["home_team"].map(rename)
    renamed["away_team"] = renamed["away_team"].map(rename)
    # The provider's own identity for the fixture, attached the same way and
    # for the same reason as the kickoff below.
    #
    # It was carried into `latest_prices` and stopped there. Every strategy
    # builds its rows from a fixed key set — `evaluate_btts` and the rest each
    # write out home_team, away_team, market, selection, odds, book and the
    # grades — so a column added to `prices` does not survive evaluation.
    # `extra_card_record` then read `row.get("provider_event_id")` off a frame
    # that had never had one and recorded the empty string, and the CLV join
    # fell back to names: the record says "Roma", the feed says "AS Roma".
    #
    # Caught only by re-auditing. The test that was supposed to cover it built
    # an `ExtraCard` straight from `latest_prices` output, which production
    # never does — the third fixture in one day to supply what production
    # drops.
    events = {
        (
            str(row["home_team"]).strip().casefold(),
            str(row["away_team"]).strip().casefold(),
            str(row["market"]).strip().casefold(),
            str(row["selection"]).strip().casefold(),
        ): str(row.get("provider_event_id") or "")
        for _, row in prices.iterrows()
    }
    selections["provider_event_id"] = [
        events.get(
            (
                str(home).strip().casefold(),
                str(away).strip().casefold(),
                str(market).strip().casefold(),
                str(selection).strip().casefold(),
            ),
            "",
        )
        for home, away, market, selection in zip(
            selections["home_team"],
            selections["away_team"],
            selections["market"],
            selections["selection"],
        )
    ]
    kickoffs = _fixture_kickoffs(renamed)
    selections["kickoff_time"] = [
        kickoffs.get(
            (str(home).strip().casefold(), str(away).strip().casefold())
        )
        for home, away in zip(selections["home_team"], selections["away_team"])
    ]
    return ExtraCard(selections, notes, priced=len(records), unrated=unrated, gate=gate)


def render_extra_card(cards: dict[str, ExtraCard]) -> list[str]:
    """Markdown for the competitions beyond the Premier League."""
    lines: list[str] = [f"## {BEYOND_SECTION_NAME}", ""]
    # Deliberately count-free. This read "Neither competition below" and was
    # written when there were two; it survived the Europa League, the
    # Conference League and the Nations League being added and went out on a
    # card carrying five, telling the reader there were two. A sentence that
    # counts its own sections has to be revisited every time one is added, and
    # is revisited only when somebody notices. The per-competition notes carry
    # the specifics, and those are edited in the same commit as the section
    # they describe.
    lines += [
        "Nothing below has been shown to beat a price. Some of it has been "
        "shown not to, and some of it cannot be tested at all. Each section "
        f"says which. They are staked at {EXTRA_UNITS} units for that reason. "
        "See `data/outputs/unified_ratings.md` and "
        "`data/outputs/european_ratings.md`.",
        "",
    ]
    fitted_only = [
        (COMPETITIONS[key].name, card)
        for key, card in cards.items()
        if not card.carded
    ]
    for key, card in cards.items():
        if not card.carded:
            continue
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

    if fitted_only:
        # Named rather than silently absent: a competition that quietly stops
        # appearing looks exactly like a week with no fixtures in it.
        described = ", ".join(
            f"{name} ({card.priced} of {card.fixtures} fixtures rateable)"
            for name, card in fitted_only
        )
        lines += [
            f"_Fitted but not bet: {described}. Their results still bridge the "
            "countries in the rating pool — which is most of their value — and "
            "they return to the card on their own the run they can price "
            "something._",
            "",
        ]
    return lines


#: Where the machine-readable record of this section lives, mirroring
#: `card_history.ARCHIVE_ROOT` for the Premier League card.
EXTRA_CARD_JSON_FILENAME = EXTRA_CARD_JSON

#: What this section is called wherever it is referred to from outside it.
#: The scoreboard has to name it to say it is not counted, and a second
#: spelling of the name there would be one more thing to drift.
BEYOND_SECTION_NAME = "Beyond the Premier League"
EXTRA_ARCHIVE_ROOT = Path("archive") / "extra_cards"


def _kickoff_text(value: object) -> str | None:
    """An ISO kickoff, or None where there is none to record."""
    stamp = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(stamp) else stamp.isoformat()


def extra_card_record(
    cards: dict[str, ExtraCard], *, now: datetime | None = None
) -> dict[str, object]:
    """What this section recommended, in a form something can score later.

    Until this existed the section's picks were rendered to markdown and posted
    in an issue comment, and nowhere else. Prices for these competitions have
    been collected since the EFL feed started — `price_feed_extra.csv` — but
    there was no record of what was SELECTED, so closing-line value could never
    be computed for any of it, forwards or backwards.

    That matters most for the competition that needs it most. The international
    section cannot be backtested at all: no free archive carries international
    prices. Forward CLV is its only possible evidence, so without this record it
    could never be shown to be good or bad, in either direction, ever.

    Written for every run including empty ones. A run that selected nothing is a
    fact about that day worth keeping — the alternative is a gap that cannot be
    told apart from a run that did not happen.
    """
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rows: list[dict[str, object]] = []
    for key, card in cards.items():
        spec = COMPETITIONS[key]
        for row in card.selections.to_dict("records"):
            rows.append(
                {
                    "competition": key,
                    "competition_name": spec.name,
                    "pool": spec.pool,
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "market": row.get("market"),
                    "selection": row.get("selection"),
                    "american_odds": row.get("american_odds"),
                    "book": row.get("book"),
                    # The provider's own identity for the fixture. The record
                    # stores mapped club names and the feed stores the
                    # provider's, so this is what lets closing-line value be
                    # joined back without re-deriving the name map.
                    "provider_event_id": row.get("provider_event_id") or "",
                    # The kickoff, so the record can be audited against the
                    # moment it was written. Without it a stale selection is
                    # only visible by going back to the price feed and hoping
                    # the fixture is still in it.
                    "kickoff_time": _kickoff_text(row.get("kickoff_time")),
                    "calibrated_edge": row.get("calibrated_edge"),
                    "raw_edge": row.get("raw_edge"),
                    "suggested_units": row.get("suggested_units"),
                }
            )
    return {
        "generated_at": moment.isoformat(),
        "selections": rows,
        "competitions": {
            key: {
                "priced": card.priced,
                "declined": list(card.unrated),
                "selections": int(len(card.selections)),
            }
            for key, card in cards.items()
        },
    }


def uncounted_beyond(output_dir: Path | None = None) -> "UncountedSection | None":
    """This section's staked selections, for the record that leaves them out.

    The record built from `archive/automated_cards` is Premier League only,
    and the email prints it below this section's table — every row of which
    carries a stake. Counting them here is not scoring them; it is refusing to
    let a reader assume the denominator covers what sits above it.

    Returns None when there is nothing to disclose: no record on disk, or a
    record with nothing staked in it. A run that selected nothing should not
    print a sentence about zero selections.
    """
    from epl_betting_lab.reports.card_scoreboard import UncountedSection

    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    path = outputs / EXTRA_CARD_JSON_FILENAME
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    staked = 0
    for row in record.get("selections", []):
        try:
            units = float(row.get("suggested_units") or 0)
        except (TypeError, ValueError):
            continue
        if units > 0:
            staked += 1
    if staked <= 0:
        return None
    return UncountedSection(name=BEYOND_SECTION_NAME, staked=staked)


def save_extra_card_record(
    cards: dict[str, ExtraCard],
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Write the record and archive a timestamped copy of it."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    outputs.mkdir(parents=True, exist_ok=True)
    record = extra_card_record(cards, now=now)

    body = json.dumps(record, indent=2, sort_keys=True, default=str) + "\n"
    (outputs / EXTRA_CARD_JSON_FILENAME).write_text(body, encoding="utf-8")

    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    directory = (
        outputs
        / EXTRA_ARCHIVE_ROOT
        / moment.strftime("%Y-%m-%d")
        / moment.strftime("%H%M%S")
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / EXTRA_CARD_JSON_FILENAME).write_text(body, encoding="utf-8")
    return record
