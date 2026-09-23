"""International results, which are a different game from the club one.

The club pools work because a club is a stable thing: it plays 38 league
matches a season with roughly the same eleven, at a ground it owns. None of
that holds for a national team, and three differences are large enough to
change the model rather than just its inputs.

**A third of competitive internationals are played on neutral ground.** No club
fixture in this project ever is. `PoissonGoalsModel` carries its home advantage
in two separately fitted baselines, `avg_home_goals` and `avg_away_goals`, and
applying those to a neutral fixture credits the nominal home side with an
advantage it does not have. Measured on this archive, competitive matches since
2018:

    real venue   n=4001   home 1.693  away 1.089   advantage +0.604 goals
    neutral      n=1977   home 1.459  away 1.360   advantage +0.099 goals

Half a goal, on a third of the fixtures. That is why `neutral` is carried on
every row here rather than dropped, and why the international pool fits its
baselines twice. A model that ignored the column would not fail — it would
quietly price every neutral fixture wrong in the same direction.

**Friendlies are a different competition wearing the same name.** 2,269 of them
since 2018 against 5,978 competitive matches, and in them teams make wholesale
substitutions and experiment. They are tagged rather than silently mixed in, so
the weight they carry is a decision someone made on purpose.

**A national team plays about ten matches a year**, against 38-plus for a club,
and its squad turns over completely every few years. Ratings fitted here rest on
far less evidence per team than any club rating in this project.

**The archive runs about a month behind, and that is load-bearing.** Read on
2026-09-23 it ended 2026-08-26 and held no September fixtures of any kind — not
even the UEFA Nations League matches this project was pricing 45 of that day. Two
consequences, and the second is the one that bites.

The obvious one: ratings never include the current international window, so by a
window's third matchday the model has not seen the first two.

The one that already caused a wrong answer: **absence here is not evidence a
competition is dormant.** Asked whether the CONCACAF Nations League was still
being played, this module's silence was read as "no", when it could not have
shown a September fixture either way. `providers/competition_watch.py` carries
that correction.

`InternationalPool.latest_result` exposes the cut-off so a caller can say how
stale it is rather than implying it is current.

Source: the `martj42/international_results` archive, which publishes every
international since the first one in 1872 as a single CSV — date, both teams,
both scores, the tournament, the city and country, and whether the venue was
neutral. It is results only. There are no odds in it, and that is the reason
this competition cannot be backtested the way the EFL was: Football-Data.co.uk
ships closing prices beside every club result, and nothing comparable exists
free for internationals.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd
import requests

SOURCE_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)

#: The archive's `tournament` string -> this project's competition code.
#:
#: Written out rather than pattern-matched. "UEFA Nations League" and
#: "CONCACAF Nations League qualification" both contain "Nations League" and are
#: not the same competition, and `data/european_clubs.py` already records what
#: happens when a name is guessed instead of declared.
COMPETITION_OF = {
    "UEFA Nations League": "UNL",
    "CONCACAF Nations League": "CNL",
    "CONCACAF Nations League qualification": "CNLQ",
    "FIFA World Cup": "WC",
    "FIFA World Cup qualification": "WCQ",
    "UEFA Euro": "EURO",
    "UEFA Euro qualification": "EUROQ",
    "Copa América": "COPA",
    "Gold Cup": "GOLD",
    "African Cup of Nations": "AFCON",
    "African Cup of Nations qualification": "AFCONQ",
    "AFC Asian Cup": "ASIAN",
    "AFC Asian Cup qualification": "ASIANQ",
    "Friendly": "FRIENDLY",
}

#: Everything else in the archive — regional cups, island games, tournaments for
#: teams outside FIFA. Kept under one code rather than dropped: they are real
#: matches between rateable sides and they inform a rating, but nothing in this
#: project will ever price one.
OTHER = "OTHER"

#: Competitions that are not a competitive fixture, however they are labelled.
FRIENDLY_CODES = frozenset({"FRIENDLY"})

COLUMNS = [
    "date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "competition",
    "tournament",
    "neutral",
]


class InternationalResultsUnavailable(RuntimeError):
    """The archive could not be read.

    Raised rather than returning an empty frame. An empty result would leave
    every national team unrated, which a caller cannot tell apart from a
    calendar with no internationals in it.
    """


@dataclass(frozen=True)
class InternationalResults:
    matches: pd.DataFrame

    @property
    def competitive(self) -> pd.DataFrame:
        """Everything that was not a friendly."""
        return self.matches[~self.matches["competition"].isin(FRIENDLY_CODES)]


def fetch_archive(*, timeout: int = 60) -> str:
    """The archive as CSV text."""
    try:
        response = requests.get(SOURCE_URL, timeout=timeout)
    except requests.RequestException as exc:
        raise InternationalResultsUnavailable(
            f"{SOURCE_URL} could not be read: {exc}"
        ) from exc
    if response.status_code != 200:
        raise InternationalResultsUnavailable(
            f"{SOURCE_URL} returned HTTP {response.status_code}."
        )
    return response.text


def parse_archive(text: str, *, since: str | None = None) -> InternationalResults:
    """Every international in the archive, as this project's column names.

    `since` trims the history. The archive starts in 1872 and a match from
    then tells you nothing about a squad assembled this month, but the cut is
    the caller's to make rather than a constant here.
    """
    try:
        frame = pd.read_csv(io.StringIO(text))
    except Exception as exc:  # pragma: no cover - pandas raises several types
        raise InternationalResultsUnavailable(
            f"The archive could not be parsed: {exc}"
        ) from exc

    required = {"date", "home_team", "away_team", "home_score", "away_score",
                "tournament", "neutral"}
    missing = required - set(frame.columns)
    if missing:
        raise InternationalResultsUnavailable(
            f"The archive is missing {sorted(missing)}, so its shape has changed "
            "and every row would be parsed wrong."
        )

    frame = frame.rename(columns={"home_score": "home_goals", "away_score": "away_goals"})
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "home_goals", "away_goals"])
    # A played match with no score is not a 0-0, and a scheduled fixture is not
    # a result. Both are dropped above rather than filled.
    frame["home_goals"] = frame["home_goals"].astype(int)
    frame["away_goals"] = frame["away_goals"].astype(int)
    # The archive writes TRUE/FALSE. Reading it as a string leaves every value
    # truthy, which would mark every fixture neutral and erase home advantage
    # from the whole pool.
    frame["neutral"] = frame["neutral"].astype(str).str.upper().eq("TRUE")
    frame["competition"] = frame["tournament"].map(COMPETITION_OF).fillna(OTHER)

    if since is not None:
        frame = frame[frame["date"] >= pd.Timestamp(since)]

    frame = frame.sort_values("date").reset_index(drop=True)
    return InternationalResults(frame[COLUMNS])


def load_international_results(
    *, since: str | None = None, fetcher=fetch_archive
) -> InternationalResults:
    """Fetch and parse in one call."""
    return parse_archive(fetcher(), since=since)
