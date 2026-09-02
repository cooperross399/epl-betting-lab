"""Upcoming EPL fixtures, from Football-Data's own fixtures feed.

`data/manual/upcoming_fixtures.csv` used to be typed by hand, and the card can
only see as far as that file goes. That is a standing appointment nobody wants
to keep: when the file runs out, the selected window has nothing upcoming to
find, every provider price falls outside it, and the card goes quiet in a way
that looks like a provider fault. The hand-typed copy was also simply wrong on
2026-08-28 — it had Aston Villa v Arsenal on the 29th when the fixture is on
the 31st.

Football-Data publishes the coming fixtures at a fixed URL, in the same team
naming the historical results use, so no mapping is needed and the model's
vocabulary cannot drift from the card's.

**This deliberately does not come from the odds provider.** `upcoming_fixtures`
is the denominator the shadow verifier uses to ask whether the provider covered
the slate. Filling it from the provider would make that check compare the
provider against itself and always pass — a gate that cannot fail is not a
gate. An independent source keeps the question real.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import requests

from epl_betting_lab.config import LEAGUE_CODE


FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

#: Columns the card pipeline reads. `notes` is kept so the file's shape does
#: not change under readers that were written against the hand-filled version.
FIXTURE_COLUMNS = ("date", "home_team", "away_team", "notes")


class FixturesUnavailable(RuntimeError):
    """The feed could not be read.

    Raised rather than returning an empty frame: an empty result written over
    the file would erase the slate, and a slate erased silently is the exact
    failure this module exists to end.
    """


class NoUpcomingFixtures(FixturesUnavailable):
    """The feed was read fine and simply lists no fixture for this league yet.

    Football-Data publishes only the coming round, so during an international
    break the file has nothing for the Premier League. That is a quiet week,
    not a fault: the previous slate is kept and the run is not degraded. It
    became a degradation once, and every off-week run went red for it — which
    is how a reader learns to ignore red.
    """


def _looks_like_a_fixtures_csv(content: bytes) -> bool:
    """Is this the CSV we asked for, or a page saying it is not there?

    Football-Data answers some requests with an HTML redirect page rather than
    a 404, and `raise_for_status` is silent on 3xx. Without this check that
    page is parsed as if it were fixtures.
    """
    head = content[:2048].lstrip().lower()
    if head.startswith(b"<"):
        return False
    return b"hometeam" in head and b"awayteam" in head


def parse_fixtures(
    content: bytes, *, league: str = LEAGUE_CODE, today: date | None = None
) -> pd.DataFrame:
    """Rows for `league` kicking off today or later, oldest first."""
    if not _looks_like_a_fixtures_csv(content):
        raise FixturesUnavailable(
            f"{FIXTURES_URL} returned {len(content)} bytes that are not a "
            "fixtures CSV."
        )
    from io import BytesIO

    frame = pd.read_csv(BytesIO(content), encoding="utf-8-sig")
    for column in ("Div", "Date", "HomeTeam", "AwayTeam"):
        if column not in frame.columns:
            raise FixturesUnavailable(
                f"The fixtures feed has no `{column}` column."
            )

    frame = frame[frame["Div"].astype(str).str.strip() == league]
    # Football-Data writes dates as DD/MM/YYYY. Left to infer, pandas reads
    # 03/08/2026 as March and silently moves the fixture five months.
    parsed = pd.to_datetime(frame["Date"], format="%d/%m/%Y", errors="coerce")
    frame = frame.assign(date=parsed.dt.date).dropna(subset=["date"])

    moment = today or date.today()
    frame = frame[frame["date"] >= moment]
    if frame.empty:
        raise NoUpcomingFixtures(
            f"The fixtures feed holds no {league} fixture on or after "
            f"{moment.isoformat()}."
        )

    built = pd.DataFrame(
        {
            "date": [d.isoformat() for d in frame["date"]],
            "home_team": frame["HomeTeam"].astype(str).str.strip().values,
            "away_team": frame["AwayTeam"].astype(str).str.strip().values,
            "notes": "",
        }
    )
    built = built[list(FIXTURE_COLUMNS)]
    built = built.drop_duplicates(subset=["date", "home_team", "away_team"])
    return built.sort_values(["date", "home_team"]).reset_index(drop=True)


def fetch_upcoming_fixtures(
    *, league: str = LEAGUE_CODE, today: date | None = None, timeout: int = 30
) -> pd.DataFrame:
    """Download the fixtures feed and return the rows for `league`."""
    try:
        response = requests.get(FIXTURES_URL, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FixturesUnavailable(f"{FIXTURES_URL} could not be read: {exc}") from exc
    return parse_fixtures(response.content, league=league, today=today)
