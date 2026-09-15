#!/usr/bin/env python
"""Observe prices in the competitions the card does not bet.

Prices are the one input that cannot be recovered later. A model can be refitted
and a rule re-run over stored prices at any time, but a price nobody wrote down
on the day is gone. So this collects prices and nothing else: it makes no
selection, publishes no card, and recommends no bet.

**Why this exists at all, given the EFL backtest said no.** The walk-forward on
Football-Data's own closing prices returned -2.0% to -2.9% at the best price
across the panel, and the one card market it could measure there (`total_2_5`)
came back decisively negative. That is the answer for the three markets
Football-Data quotes; it is not an answer for the five it does not.

**And the first live run narrowed that considerably.** The case made for this
collection was corners: three of the seven markets the card stakes, with no free
price history in any division, ever. The provider does not carry them for the
EFL. Asked for all eight in the same run that returned all eight for the Premier
League, the EFL answered with `1x2`, `btts` and `total_2_5` — no corners, no
double chance, no draw-no-bet.

What survives of the case is one market. `btts` has no free historical price in
any division, so a forward record is the only evidence it can ever have, and the
EFL now contributes one. `total_2_5` and `1x2` were already available free from
Football-Data. Corners cannot be evidenced forward here either.

That is a much smaller reason than the one this file was written for, and it is
recorded here rather than left in a commit message nobody re-reads.

**It is deliberately kept away from the card.** Three separations, each of which
would be a real fault if it were missing:

*It never writes the staging bundle.* `run_provider_shadow_verification.py`
fetches with `--overwrite-staging`, which replaces `data/staging/` — the bundle
the card is built from. Pointing that at an EFL sport key would put EFL prices
where the card looks for Premier League ones. Here the provider is given an
explicit `repository_root` in a temporary directory, which is a supported path
through its own guard rather than a way around one, so the real `data/staging/`
is never touched.

*It writes its own feed.* These rows go to `price_feed_extra.csv`, not the feed
the live card's CLV is measured from. Nothing in this project carries a competition
on a row — every identity is `(date, home_team, away_team)` — so two
competitions in one file would be distinguishable only by club name. A separate
file cannot be got wrong. The `competition` column is written anyway, because a
file can be moved and a column travels with the row.

*It signs nothing.* The provider policy's acceptance receipt is keyed on the
provider, not the competition, and the evidence bundle behind it only ever
examined Premier League coverage. Collecting observations is not promoting
evidence, so no receipt is needed and none is created.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import DIVISION_NAMES, EFL_DIVISIONS, PROCESSED_DIR

#: Names for the competitions that are not Football-Data divisions, so a report
#: does not have to print a bare key at a reader.
COMPETITION_NAMES = {
    **DIVISION_NAMES,
    "UCL": "UEFA Champions League",
    # No longer collected, kept so the rows already in the feed still render
    # with a name rather than a bare key.
    "EFLC": "EFL Cup (Carabao)",
}
from epl_betting_lab.providers import create_provider
from epl_betting_lab.providers.base import ProviderRunRequest
from epl_betting_lab.reports.price_feed import (
    FEED_COLUMNS,
    append_snapshot,
    load_feed,
    save_feed,
    snapshot_rows,
)

#: Football-Data division code -> The Odds API sport key.
#:
#: Written out rather than derived. A mapping that is computed from a naming
#: convention silently produces a plausible-looking key for a competition the
#: provider does not carry, and the fetch then returns an empty list that reads
#: exactly like a quiet week.
SPORT_KEYS = {
    "E1": "soccer_efl_champ",
    "E2": "soccer_england_league1",
    "E3": "soccer_england_league2",
    # Not a division, and deliberately not modelled. The ratings refuse a club
    # they have never seen (`UnratedTeam`), and a Champions League tie is two
    # clubs from pools with no common scale — which is the whole reason nothing
    # here makes a selection. Prices are collected because they cannot be
    # recovered later and a rule can always be re-run over them; a rule that
    # could price these fixtures does not exist yet and may never.
    #
    # It earns its place on coverage. Asked for all eight card markets, the
    # Champions League returned all eight — 945 observations across 18
    # league-phase fixtures, including every corner market. It is the only
    # competition outside the Premier League that does. Corners are three of
    # the seven markets the card stakes and no source retains their prices
    # historically, so this is the only place they can be watched at all
    # outside the EPL. Thin, though: those corner prices came from a single
    # book, so there is no cross-book dispersion in them to read.
    #
    # Worth knowing before reading anything into what arrives: Football-Data
    # publishes no UEFA competition at all, so nothing collected here can ever
    # be settled from a free source. Closing-line value needs no result and
    # remains possible; profit does not.
    "UCL": "soccer_uefa_champs_league",
}

#: Collected once, then stopped. `soccer_england_efl_cup` returned `1x2`,
#: `btts` and `total_2_5` and nothing else — the same thin three the EFL gives,
#: from a competition with no free results source and no model that can price
#: it. It duplicated what E1/E2/E3 already provide at additional cost.
#:
#: Its 236 observations stay in the feed under `competition = EFLC`. They are
#: real prices, honestly collected, and removing them would be tidying away
#: evidence rather than correcting anything.
WITHDRAWN_KEYS = {"EFLC": "soccer_england_efl_cup"}

#: What the card bets and this collection therefore asks for. Compared against
#: what actually comes back, so a market the provider does not carry cannot be
#: mistaken for one nobody requested.
EXPECTED_MARKETS = (
    "1x2",
    "btts",
    "double_chance",
    "draw_no_bet",
    "total_2_5",
    "corners_1x2",
    "corners_total_9_5",
    "corners_total_10_5",
)

#: Renamed from `price_feed_efl.csv` once it began carrying the Champions
#: League as well, because a file named for one competition while holding
#: another is a trap for whoever reads it next. The restore migrates the old
#: name across on first sight and then stops publishing it.
DEFAULT_FEED = PROCESSED_DIR / "price_feed_extra.csv"

#: The feed's own columns plus the one thing the project has never carried.
EFL_FEED_COLUMNS = ("competition",) + tuple(FEED_COLUMNS)


def collect_division(
    division: str,
    *,
    regions: str = "us",
    include_event_markets: bool = True,
) -> tuple[pd.DataFrame, str]:
    """Fetch one division's prices into memory. Writes nothing outside a tempdir."""
    sport_key = SPORT_KEYS[division]
    provider = create_provider(
        "odds_api",
        sport_key=sport_key,
        regions=regions,
        include_event_markets=include_event_markets,
    )
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        (root / "data" / "staging").mkdir(parents=True, exist_ok=True)
        (root / "data" / "outputs").mkdir(parents=True, exist_ok=True)
        provider.run(
            ProviderRunRequest(
                dry_run=False,
                overwrite_staging=True,
                repository_root=root,
                generated_by="scripts/collect_extra_competitions.py",
                notes=f"Price observation for {division} ({sport_key}).",
            )
        )
        staged = root / "data" / "staging" / "current_odds_staging.csv"
        provenance_path = root / "data" / "staging" / "staging_provenance.json"
        if not staged.is_file() or not provenance_path.is_file():
            return pd.DataFrame(columns=list(EFL_FEED_COLUMNS)), (
                f"{division}: the provider returned no staging bundle."
            )
        odds = pd.read_csv(staged)
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

    rows = snapshot_rows(odds, provenance)
    if rows.empty:
        # An empty answer and a failed one are different facts, and this is the
        # empty one: the request worked and the provider had nothing priced.
        return pd.DataFrame(columns=list(EFL_FEED_COLUMNS)), (
            f"{division}: the provider answered with no usable price."
        )
    rows = rows.copy()
    rows["competition"] = division
    note = (
        f"{division} ({COMPETITION_NAMES[division]}): {len(rows):,} observations "
        f"across {rows.groupby(['home_team', 'away_team']).ngroups} fixtures — "
        f"{', '.join(sorted(rows['market'].unique()))}."
    )
    absent = sorted(set(EXPECTED_MARKETS) - set(rows["market"].unique()))
    if absent:
        # The whole case for collecting the EFL rested on corners, which no
        # source retains historically. The first live run returned 1x2, btts
        # and total_2_5 and nothing else, and that was discovered by diffing
        # this feed against the Premier League one rather than being told.
        #
        # A market the provider does not carry looks exactly like a market
        # nobody asked for, so the difference between what was requested and
        # what came back is said out loud every run.
        note += (
            f"\n  {division}: requested but not returned — {', '.join(absent)}. "
            "The provider carries these for the Premier League and not here, so "
            "they cannot be evidenced forward in this competition either."
        )
    return rows[list(EFL_FEED_COLUMNS)], note


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--divisions",
        nargs="+",
        default=sorted(SPORT_KEYS),
        choices=sorted(SPORT_KEYS),
    )
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--regions", default="us")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually fetch. Without it nothing is requested and no quota is "
        "spent — the default is deliberately inert, as everywhere else here.",
    )
    args = parser.parse_args()

    if not args.live:
        print(
            "Dry run: no request was made and no quota spent. Divisions that "
            f"would be fetched: {', '.join(f'{d} -> {SPORT_KEYS[d]}' for d in args.divisions)}"
        )
        return 0

    feed = load_feed(args.feed)
    if "competition" not in feed.columns:
        feed["competition"] = pd.NA
    feed = feed.reindex(columns=list(EFL_FEED_COLUMNS))

    before = len(feed)
    failures: list[str] = []
    for division in args.divisions:
        try:
            rows, note = collect_division(division, regions=args.regions)
        except Exception as exc:
            # One division failing must not discard the others. A partial
            # collection is reported and exits non-zero; it is not rounded up.
            print(f"{division}: could not be collected: {exc}")
            failures.append(division)
            continue
        print(note)
        feed = append_snapshot(feed, rows).reindex(columns=list(EFL_FEED_COLUMNS))

    added = len(feed) - before
    save_feed(feed, args.feed)
    print(f"Added {added:,} new observation(s); the feed holds {len(feed):,}.")

    if failures:
        print(f"Divisions that failed: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
