#!/usr/bin/env python3
"""Build `board.json` for the EPL page of the Maverick Hightower projections site.

    PYTHONPATH=src python web/build_board_json.py --lab . --out dist/data

Runs INSIDE epl-betting-lab, after Matchday Refresh, with that run's
`matchday-state` / `matchday-reports` artifacts restored into data/. Publishes
to this repository's own GitHub Pages; the site (hosted from nhl-betting-lab)
reads https://cooperross399.github.io/epl-betting-lab/data/board.json in the
browser. No cross-repository token exists anywhere in this chain.

Sources, as they are actually named in this repository:

  * ESPN's public soccer scoreboard (keyless): fixtures in the card's window,
    kickoff, venue, broadcast, form. The month form of `?dates=` is used
    because the documented range form `?dates=A-B` answers HTTP 400 on the
    soccer endpoint.
  * The card. `data/outputs/automated_card.json` when a run wrote it here,
    otherwise the newest archived copy under
    `data/outputs/archive/automated_cards/<date>/<time>/automated_card.json`
    — which is what the `matchday-state` artifact actually carries. The plain
    `automated_card.json` is in NEITHER artifact (`matchday-reports` uploads
    `automated_card.md`), so the archive is the only path a published run has.
  * `data/staging/` + `automated_card_input.CARD_INPUT_FILENAME`
    (`automated_card_current_odds.csv`): the provider's best bettable price
    per market/selection, columns `home_team, away_team, market, selection,
    american_odds, closing_american_odds, book, notes`. `data/staging/` is
    git-ignored and rides in no artifact, so a published run normally falls
    back to the prices carried on the card's own rows; `priceSource` says
    which was used.
  * The lab's own fitted models, exactly as `dashboard_actions.
    run_thursday_best_bets_report` fits them: `PoissonGoalsModel().fit(
    load_matches(), last_n_matches_per_team=38, config=CARD_RATINGS)` for the
    1X2 and draw-no-bet numbers, and `PoissonGoalsModel().fit(
    load_matches_with_xg(), config=TOTALS_RATINGS)` for over 2.5 and both
    teams to score — the card prices both of those off `totals_projections`.
    Keys read off `match_probabilities()`: `home_win`, `draw`, `away_win`,
    `over_2_5`, `btts_yes`, `draw_no_bet_home`, `home_xg`, `away_xg`.
  * `card_scoreboard.build_scoreboard(load_archived_cards(...), load_matches())`
    for the settled record — the same call `reports/card_notification.py` and
    `reports/run_summary.py` make for "How the recommendations have done".
    That module writes no file of its own; the record is recomputed here.

ON CALIBRATION. The card's `calibrated_model_prob` is not a property of the
model: `models/calibration.calibrate_probability` shrinks a raw probability
toward the implied probability OF THE QUOTED PRICE, and every caller
(`strategies/ml_value.py`, `totals.py`, `btts.py`, `derived_result.py`,
`count_markets.py`) passes `american_odds=` the quote it is grading. There is
therefore no price-free calibrated number to publish, and shrinking toward a
historical baseline instead would be a different calculation wearing the same
name. So the fair prices below are the model's raw probabilities, and each
fixture's `pick` carries the card's own calibrated probability and edge for
the one selection the card actually graded.

Nothing here fetches odds, spends a credit, or places a bet.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"
USER_AGENT = "epl-betting-lab-site/1.0 (+https://github.com/cooperross399/epl-betting-lab)"
SEASON = "2026–27"

#: How far ahead to look for the next round when the card names no window.
#: One international break is a fortnight; two months of schedule clears it.
LOOKAHEAD_MONTHS = 2

#: `card_scoreboard.render_scoreboard` tells the reader that separating a real
#: 5% edge from zero needs roughly this many settled bets. The page prints the
#: same denominator, so it is read from one place.
BETS_TO_ANSWER = 1500

#: `selected_slate.selected_window_label` spells a window this way.
WINDOW_SEPARATOR = " through "

#: Football-Data team string -> (abbr, short, colour, ink). Football-Data's
#: names are the model's vocabulary and this project's canonical names (see
#: providers/team_names.CANONICAL_TEAM_NAMES); ESPN's differ, hence `fd_name`.
#: All twenty 2026-27 clubs are here — Coventry, Hull and Ipswich came up and
#: Burnley, West Ham and Wolves went down. The three relegated clubs are kept
#: because the settled record and the archived cards still name them.
TEAMS = {
    "Arsenal": ("ARS", "Arsenal", "#EF0107", "#FFFFFF"),
    "Aston Villa": ("AVL", "Aston Villa", "#670E36", "#FFFFFF"),
    "Bournemouth": ("BOU", "Bournemouth", "#DA291C", "#FFFFFF"),
    "Brentford": ("BRE", "Brentford", "#E30613", "#FFFFFF"),
    "Brighton": ("BHA", "Brighton", "#0057B8", "#FFFFFF"),
    "Burnley": ("BUR", "Burnley", "#6C1D45", "#FFFFFF"),
    "Chelsea": ("CHE", "Chelsea", "#034694", "#FFFFFF"),
    "Coventry": ("COV", "Coventry", "#78D0F3", "#000000"),
    "Crystal Palace": ("CRY", "Crystal Palace", "#1B458F", "#FFFFFF"),
    "Everton": ("EVE", "Everton", "#003399", "#FFFFFF"),
    "Fulham": ("FUL", "Fulham", "#111111", "#FFFFFF"),
    "Hull": ("HUL", "Hull", "#F18A01", "#000000"),
    "Ipswich": ("IPS", "Ipswich", "#3A64A3", "#FFFFFF"),
    "Leeds": ("LEE", "Leeds", "#FFCD00", "#000000"),
    "Liverpool": ("LIV", "Liverpool", "#C8102E", "#FFFFFF"),
    "Man City": ("MCI", "Man City", "#6CABDD", "#000000"),
    "Man United": ("MUN", "Man United", "#DA291C", "#FFFFFF"),
    "Newcastle": ("NEW", "Newcastle", "#241F20", "#FFFFFF"),
    "Nott'm Forest": ("NFO", "Nott'm Forest", "#DD0000", "#FFFFFF"),
    "Sunderland": ("SUN", "Sunderland", "#EB172B", "#FFFFFF"),
    "Tottenham": ("TOT", "Tottenham", "#132257", "#FFFFFF"),
    "West Ham": ("WHU", "West Ham", "#7A263A", "#FFFFFF"),
    "Wolves": ("WOL", "Wolves", "#FDB913", "#000000"),
}

#: ESPN display name -> Football-Data name, for spellings the lab's own
#: reviewed table (providers/team_names.PROVIDER_TEAM_ALIASES) does not carry.
#: Checked on 2026-09-22 against every fixture ESPN lists for 2026-27: all 380
#: matches, all twenty clubs, and `normalize_team_name` already maps every one
#: of the ESPN spellings onto a canonical name, so this table is currently
#: empty by verification rather than by omission. It stays as the place a
#: divergence goes, because the alias table faces the odds provider and is not
#: obliged to keep ESPN working.
ESPN_TO_FD: dict[str, str] = {}


def _normalize_team_name(espn_name: str) -> str | None:
    """The lab's reviewed provider mapping, or None if it is not importable."""
    try:
        from epl_betting_lab.providers.team_names import (
            is_canonical_team_name,
            normalize_team_name,
        )
    except ImportError:
        return None
    mapped = normalize_team_name(espn_name)
    return mapped if is_canonical_team_name(mapped) else None


def fd_name(espn_name: str) -> str:
    """ESPN's display name as the model spells it.

    The lab's reviewed alias table is asked first so the two cannot disagree;
    `ESPN_TO_FD` covers anything it does not map. An unknown name is returned
    unchanged, which is the same refusal `normalize_team_name` makes: it stays
    visibly unmapped rather than being coerced onto the wrong club.
    """
    cleaned = " ".join(str(espn_name or "").split())
    mapped = _normalize_team_name(cleaned)
    if mapped is not None:
        return mapped
    return ESPN_TO_FD.get(cleaned, cleaned)


def team_entry(fd: str) -> tuple[str, dict]:
    abbr, short, color, fg = TEAMS.get(fd, (fd[:3].upper(), fd, "#14151a", "#FFFFFF"))
    return abbr, {"name": fd, "short": short, "color": color, "fg": fg}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - fixed host
        return json.load(resp)


def month_codes(start: date, end: date) -> list[str]:
    """`YYYYMM` for every month the span touches, in order."""
    codes: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        codes.append(f"{year:04d}{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return codes


def fetch_fixtures(months: list[str]) -> tuple[list[dict], list[str]]:
    """Every EPL fixture ESPN lists in those months, plus any month that failed.

    A month at a time, because `?dates=20260926-20261002` — the range form
    every other ESPN endpoint takes — answers HTTP 400 here. Verified on
    2026-09-22: the range 400s, `?dates=202609` returns the month.
    """
    out: list[dict] = []
    failed: list[str] = []
    for code in months:
        try:
            payload = fetch_json(f"{ESPN}?dates={code}&limit=200")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"ESPN month {code} could not be read: {exc}")
            failed.append(code)
            continue
        for ev in payload.get("events", []):
            comp = (ev.get("competitions") or [{}])[0]
            sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            h, a = sides.get("home", {}), sides.get("away", {})
            names = {b.get("names", [""])[0] for b in comp.get("broadcasts", []) if b.get("names")}
            kickoff = str(ev.get("date") or "")
            out.append({
                "id": str(ev.get("id")), "kickoff": kickoff, "date": kickoff[:10],
                "venue": (comp.get("venue") or {}).get("fullName", ""),
                "city": ((comp.get("venue") or {}).get("address") or {}).get("city", ""),
                "tv": " / ".join(sorted(names)) or "—",
                "state": ((ev.get("status") or {}).get("type") or {}).get("state", "pre"),
                "home": {"fd": fd_name((h.get("team") or {}).get("displayName", "")), "form": h.get("form", "")},
                "away": {"fd": fd_name((a.get("team") or {}).get("displayName", "")), "form": a.get("form", "")},
            })
    out.sort(key=lambda f: (f["kickoff"], f["id"]))
    return out, failed


#: `PoissonGoalsModel.fit` clamps a club's attack and defence at this value
#: (models/poisson_goals.py:181, `max(attack, 0.2)`). A club sitting on the
#: floor does not have a weak rating — it has a rating the floor invented,
#: because too few top-flight games exist to measure one. Coventry, five
#: games up from the Championship, projects 0.28 goals and a fair home price
#: of +3434 against Newcastle. That is not a projection anyone should read.
#:
#: The class already refuses a club it has never seen rather than
#: substituting an average side. This is the same refusal one step milder.
RATING_FLOOR = 0.2


def to_american(p: float) -> int:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return round(-100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def read_card(lab: Path) -> tuple[dict, str]:
    """This run's card, and where it was read from.

    `data/outputs/automated_card.json` is what a local run leaves behind. A
    published run has only what the artifacts carry, and neither carries that
    file — `matchday-reports` uploads `automated_card.md` and `matchday-state`
    uploads `data/outputs/archive/automated_cards`. So the archive is the
    fallback, newest first, read with the card archive's own layout
    (`card_history.ARCHIVE_ROOT` / date / time / automated_card.json).
    """
    outputs = lab / "data" / "outputs"
    direct = outputs / "automated_card.json"
    if direct.is_file():
        card = _read_json(direct)
        if card:
            return card, "data/outputs/automated_card.json"
    archived = sorted((outputs / "archive" / "automated_cards").glob("*/*/automated_card.json"))
    for path in reversed(archived):
        card = _read_json(path)
        if card:
            return card, str(path.relative_to(lab)) if path.is_relative_to(lab) else str(path)
    return {}, "no card on disk"


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _price_row(row: dict) -> dict | None:
    """One quote in the shape `best_price` compares, or None if it is not one."""
    home = str(row.get("home_team") or "").strip()
    away = str(row.get("away_team") or "").strip()
    market = str(row.get("market") or "").strip().casefold()
    selection = str(row.get("selection") or "").strip().casefold()
    if not (home and away and market and selection):
        return None
    try:
        american = float(row.get("american_odds"))
    except (TypeError, ValueError):
        return None
    return {
        "home_team": home, "away_team": away, "market": market,
        "selection": selection, "american_odds": american,
        "book": str(row.get("book") or "").strip(),
    }


def read_prices(lab: Path, card: dict) -> tuple[list[dict], str]:
    """The provider prices the card was made from, and where they came from.

    The card-input file is the authority:
    `data/staging/` + `automated_card_input.CARD_INPUT_FILENAME`, one row per
    (date, home, away, market, selection) already reduced to the best bettable
    quote by `automated_card_input._best_quote`. `data/staging/` is in
    `.gitignore` and is uploaded by no workflow, so on a published run the
    file is simply absent; the card's own rows carry the same four keys and
    the same `american_odds`, for the selections the card graded, and they are
    used instead. Nothing is invented either way.
    """
    path = None
    try:
        from epl_betting_lab.reports.automated_card_input import CARD_INPUT_FILENAME
    except ImportError:
        pass
    else:
        path = lab / "data" / "staging" / CARD_INPUT_FILENAME

    if path is not None and path.is_file():
        rows: list[dict] = []
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                for raw in csv.DictReader(fh):
                    row = _price_row(raw)
                    if row is not None:
                        rows.append(row)
        except (OSError, UnicodeError, csv.Error) as exc:
            print(f"{path.name} could not be read: {exc}")
        else:
            return rows, f"data/staging/{path.name}"

    rows = []
    for section in ("best_bets", "leans", "passes_or_avoids", "already_started"):
        for raw in card.get(section) or []:
            if isinstance(raw, dict):
                row = _price_row(raw)
                if row is not None:
                    rows.append(row)
    return rows, "the card's own rows" if rows else "no prices on disk"


def best_price(rows, home, away, market, selection):
    best = None
    for r in rows:
        if (r["home_team"], r["away_team"], r["market"], r["selection"]) != (home, away, market, selection):
            continue
        price = r["american_odds"]
        best = price if best is None or price > best else best
    return None if best is None else int(best)


class Projector:
    """The lab's own goals models, asked one fixture at a time.

    Two fits, because the card is two fits: `CARD_RATINGS` over
    `load_matches()` with `last_n_matches_per_team=38` prices 1X2 and
    draw-no-bet, and `TOTALS_RATINGS` over `load_matches_with_xg()` prices
    over 2.5 and both-teams-to-score. `run_thursday_best_bets_report` hands
    `totals_projections` to `evaluate_total_25_anchored` AND `evaluate_btts`,
    so BTTS is priced off the totals fit rather than off `BTTS_RATINGS`, whose
    values are identical to `TOTALS_RATINGS` anyway.
    """

    def __init__(self, result_model, goals_model, unrated_error):
        self._result = result_model
        self._goals = goals_model
        self._unrated_error = unrated_error
        #: Clubs the fit has never seen. `expected_goals` refuses them rather
        #: than substituting an average side, and so does this.
        self.unrated: set[str] = set()
        #: Clubs whose rating is the floor rather than a measurement.
        self.clamped: set[str] = set()

    def __call__(self, home: str, away: str) -> dict | None:
        try:
            result = self._result.match_probabilities(home, away)
            goals = self._goals.match_probabilities(home, away)
        except self._unrated_error:
            for team in (home, away):
                if team not in self._result.team_strengths or team not in self._goals.team_strengths:
                    self.unrated.add(team)
            return None
        floored = {
            team
            for team in (home, away)
            for strength in [self._result.team_strengths.get(team)]
            if strength is not None
            and min(float(strength.attack), float(strength.defense)) <= RATING_FLOOR
        }
        self.clamped |= floored
        return {
            "clamped": sorted(floored),
            "eh": float(result["home_xg"]), "ea": float(result["away_xg"]),
            "home": float(result["home_win"]), "draw": float(result["draw"]),
            "away": float(result["away_win"]), "dnbHome": float(result["draw_no_bet_home"]),
            "over25": float(goals["over_2_5"]), "btts": float(goals["btts_yes"]),
        }


def load_model(lab: Path) -> tuple[Projector | None, str]:
    """Fit the card's models, or say why not. Never raises: a model that
    cannot be fitted must not fail the deploy."""
    try:
        from epl_betting_lab.data.loaders import load_matches, load_matches_with_xg
        from epl_betting_lab.models.poisson_goals import (
            CARD_RATINGS,
            TOTALS_RATINGS,
            PoissonGoalsModel,
            UnratedTeam,
        )
    except ImportError as exc:
        return None, f"the lab package could not be imported ({exc})"

    processed = lab / "data" / "processed"
    matches_path = processed / "epl_historical_matches.csv"
    xg_path = processed / "understat_team_xg.csv"
    try:
        result_model = PoissonGoalsModel().fit(
            load_matches(matches_path), last_n_matches_per_team=38, config=CARD_RATINGS
        )
        goals_model = PoissonGoalsModel().fit(
            load_matches_with_xg(matches_path, xg_path), config=TOTALS_RATINGS
        )
    except Exception as exc:  # the site must never fail the deploy over the model
        return None, f"the goals model could not be fitted ({type(exc).__name__}: {exc})"

    note = ""
    if not xg_path.is_file():
        note = (
            "Understat xG was not restored with this run, so the 2.5-goals and "
            "both-teams-to-score ratings fell back to goals for every match."
        )
    return Projector(result_model, goals_model, UnratedTeam), note


def pick_for(card: dict, home: str, away: str) -> dict | None:
    def rows(section, kind):
        return [{**r, "_kind": kind} for r in card.get(section) or []
                if r.get("home_team") == home and r.get("away_team") == away]
    mine = rows("best_bets", "bet") + rows("leans", "lean") + rows("passes_or_avoids", "pass")
    started = [r for r in card.get("already_started") or []
               if r.get("home_team") == home and r.get("away_team") == away]
    if not mine and not started:
        return None
    rank = {"bet": 0, "lean": 1, "pass": 2}
    src = mine or started
    top = sorted(src, key=lambda r: (rank.get(r.get("_kind", "pass"), 3), -float(r.get("calibrated_edge") or 0)))[0]
    kind = top.get("_kind") or ("bet" if top.get("original_section") == "Best bets" else "lean" if top.get("original_section") == "Leans" else "pass")
    return {
        "kind": kind, "market": top.get("market"), "label": selection_label(top, home, away),
        "price": int(float(top["american_odds"])) if top.get("american_odds") not in (None, "") else None,
        "book": top.get("book"), "tier": top.get("confidence_tier") if kind == "bet" else None,
        "units": float(top["suggested_units"]) if kind == "bet" and top.get("suggested_units") not in (None, "") else None,
        "edgePct": round(100 * float(top["calibrated_edge"]), 1) if top.get("calibrated_edge") not in (None, "") else None,
        "modelProb": round(float(top["calibrated_model_prob"]), 4) if top.get("calibrated_model_prob") not in (None, "") else None,
        "betDownTo": int(float(top["bet_down_to_american"])) if top.get("bet_down_to_american") not in (None, "") else None,
    }


def selection_label(r: dict, home: str, away: str) -> str:
    """Market and selection in words. The selection spellings are
    `market_eligibility.MARKET_SELECTIONS`, which is where `draw_or_away`
    comes from — the card never writes `away_or_draw`."""
    m, s = (r.get("market") or "").lower(), (r.get("selection") or "").lower()
    side = {"home": home, "away": away}.get(s, s.replace("_", " "))
    if m == "total_2_5":
        return f"{s.capitalize()} 2.5"
    if m == "btts":
        return "Both teams score" if s in ("yes", "over") else "Not both to score"
    if m == "draw_no_bet":
        return f"{side} draw no bet"
    if m == "double_chance":
        return {"home_or_draw": f"{home} or draw", "draw_or_away": f"{away} or draw", "home_or_away": "No draw"}.get(s, s)
    if m == "corners_1x2":
        return "Corners level" if s == "draw" else f"{side} most corners"
    if m.startswith("corners_total_"):
        return f"{s.capitalize()} {m.rsplit('_', 2)[-2]}.{m.rsplit('_', 1)[-1]} corners"
    return f"{side} {m}"


def load_record(lab: Path) -> dict:
    """The card's own settled record, recomputed the way the card comment does.

    `reports/card_scoreboard.py` writes no file: `card_notification.py` and
    `run_summary.py` both call
    `build_scoreboard(load_archived_cards(outputs/"archive"/"automated_cards"),
    load_matches())` at print time and render the lines under "How the
    recommendations have done". The same call is made here, so the board and
    the emailed card cannot report different numbers.

    `unsettleable` and `kickoffUnknown` are carried because the card prints
    them: a selection with no settlement rule never resolves, and folding it
    into `pending` is the exact misstatement that module exists to prevent.
    """
    out = {
        "settled": 0, "won": 0, "stakedUnits": 0.0, "profitUnits": 0.0, "roiPct": None,
        "pending": 0, "awaitingResults": 0, "void": 0, "unsettleable": 0,
        "kickoffUnknown": 0, "clvPct": None, "betsToAnswer": BETS_TO_ANSWER,
    }
    try:
        import pandas as pd

        from epl_betting_lab.data.loaders import load_matches
        from epl_betting_lab.reports.card_scoreboard import build_scoreboard, load_archived_cards
    except ImportError as exc:
        print(f"the settled record is unavailable: {exc}")
        return out

    cards = load_archived_cards(lab / "data" / "outputs" / "archive" / "automated_cards")
    if not cards:
        return out
    try:
        results = load_matches(lab / "data" / "processed" / "epl_historical_matches.csv")
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"no results on disk, so nothing settles: {exc}")
        results = pd.DataFrame()

    board = build_scoreboard(cards, results)
    settled = board.settled
    out.update(
        settled=len(settled),
        won=sum(1 for s in settled if s.won),
        stakedUnits=round(board.staked_units, 2),
        profitUnits=round(board.profit_units, 2),
        pending=board.pending,
        awaitingResults=board.awaiting_results,
        void=board.void,
        unsettleable=board.unsettleable,
        kickoffUnknown=board.kickoff_unknown,
    )
    if board.roi is not None:
        out["roiPct"] = round(100 * board.roi, 1)
    return out


def unit_dollars() -> float:
    try:
        from epl_betting_lab.config import BANKROLL_UNIT_DOLLARS
    except ImportError:
        return 25.0
    return float(BANKROLL_UNIT_DOLLARS)


def card_window(card: dict) -> tuple[date, date] | None:
    """The round the card is about, parsed from its own window label.

    `selected_slate.selected_window_label` writes "2026-10-10 through
    2026-10-12", and `automated_card` copies it into `window_label`. An
    unusable window ("no dated fixtures") returns None.
    """
    label = str(card.get("window_label") or "")
    if WINDOW_SEPARATOR not in label:
        return None
    start_text, _, end_text = label.partition(WINDOW_SEPARATOR)
    try:
        return date.fromisoformat(start_text.strip()), date.fromisoformat(end_text.strip())
    except ValueError:
        return None


def slate_window(fixtures: list[dict], today: date) -> tuple[date, date] | None:
    """The next round in the fetched schedule, by the lab's own definition.

    `selected_slate.selected_window` is the single definition of the window
    that separates one round from the next, and every report imports it so
    they cannot disagree. Used only when the card names no window — an
    international break means "today plus six days" can be an empty board
    while the next round sits three weeks out.
    """
    if not fixtures:
        return None
    try:
        import pandas as pd

        from epl_betting_lab.selected_slate import selected_window
    except ImportError:
        return None
    return selected_window(pd.Series([f["date"] for f in fixtures]), today=today)


def build(lab: Path, today: date) -> dict:
    now = datetime.now(timezone.utc)
    card, card_source = read_card(lab)
    prices, price_source = read_prices(lab, card)
    project, model_note = load_model(lab)

    window = card_window(card)
    span_start = window[0] if window else today
    span_end = window[1] if window else today + timedelta(days=31 * LOOKAHEAD_MONTHS)
    fixtures, failed_months = fetch_fixtures(month_codes(span_start, span_end))
    if window is None:
        window = slate_window(fixtures, today) or (today, today + timedelta(days=6))
    start, end = window
    fixtures = [f for f in fixtures if start.isoformat() <= f["date"] <= end.isoformat()]

    excluded = [str(m).lower() for m in card.get("excluded_markets") or []]
    teams, games = {}, []
    for f in fixtures:
        h, a = f["home"]["fd"], f["away"]["fd"]
        ha, hentry = team_entry(h)
        aa, aentry = team_entry(a)
        teams.setdefault(ha, hentry)
        teams.setdefault(aa, aentry)
        row = {
            "id": f["id"], "kickoff": f["kickoff"], "venue": f["venue"], "city": f["city"],
            "tv": f["tv"], "started": f["state"] != "pre",
            "home": {"abbr": ha, "record": f["home"]["form"]},
            "away": {"abbr": aa, "record": f["away"]["form"]},
            "result": {"fair": {}, "excluded": "1x2" in excluded},
            "total": {"line": 2.5,
                      "over": best_price(prices, h, a, "total_2_5", "over"),
                      "under": best_price(prices, h, a, "total_2_5", "under")},
            "btts": {"yes": best_price(prices, h, a, "btts", "yes"),
                     "no": best_price(prices, h, a, "btts", "no")},
            "drawNoBet": {"home": best_price(prices, h, a, "draw_no_bet", "home"),
                          "away": best_price(prices, h, a, "draw_no_bet", "away")},
            "pick": pick_for(card, h, a),
        }
        pr = project(h, a) if project else None
        if pr:
            row["home"].update(projGoals=round(pr["eh"], 2), winProb=round(pr["home"], 4))
            row["away"].update(projGoals=round(pr["ea"], 2), winProb=round(pr["away"], 4))
            row["drawProb"] = round(pr["draw"], 4)
            if pr["clamped"]:
                # The goal expectation still publishes — it is the model's
                # own output and the page shows it as a projection. A fair
                # PRICE reads as something to bet into, and a price derived
                # from a floor is not that.
                row["result"]["fairUnavailable"] = (
                    "rating at the model's floor for "
                    + ", ".join(pr["clamped"])
                )
            else:
                row["result"]["fair"] = {"home": to_american(pr["home"]),
                                         "draw": to_american(pr["draw"]),
                                         "away": to_american(pr["away"])}
            row["drawNoBet"]["homeProb"] = round(pr["dnbHome"], 4)
            row["total"]["overProb"] = round(pr["over25"], 4)
            row["btts"]["yesProb"] = round(pr["btts"], 4)
        games.append(row)

    notices = []
    if not games:
        notices.append(
            f"No Premier League fixture falls in {start.isoformat()} – {end.isoformat()}."
        )
    if failed_months:
        notices.append("The schedule feed did not answer for " + ", ".join(failed_months) + ".")
    if not card.get("card_generated"):
        notices.append(
            "The card did not generate this run: "
            + str(card.get("root_blocker") or "no card report was found")
            + ". Fixtures and model numbers are shown; no selection is."
        )
    elif not any(g["pick"] and g["pick"]["kind"] == "bet" and not g["started"] for g in games):
        notices.append(
            "Nothing on this window clears the bars. That is the expected outcome "
            "for a model with no demonstrated edge."
        )
    if project is None:
        notices.append(
            "The goals model could not be fitted in this run ("
            + model_note
            + "), so projections are absent; prices and the card's picks stand."
        )
    else:
        if model_note:
            notices.append(model_note)
        if project.clamped:
            notices.append(
                "No fair price is shown for fixtures involving "
                + ", ".join(sorted(project.clamped))
                + ": too few top-flight games exist to rate them, so the "
                "model is using its own floor and any price off it would be "
                "an artifact of that floor rather than a projection. The "
                "goal expectation is still shown."
            )
        if project.unrated:
            notices.append(
                "No rating on file for " + ", ".join(sorted(project.unrated))
                + ", so those fixtures carry no projection. An average side would "
                "be a price the model has no evidence for."
            )
    if price_source == "the card's own rows":
        notices.append(
            "Provider prices are shown only for the selections the card graded: "
            "the staging file they come from is git-ignored and rides in no "
            "artifact, so a published run reads them off the card."
        )
    elif price_source == "no prices on disk":
        notices.append("No provider price reached this run, so only model numbers are shown.")

    return {
        "generatedAt": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "season": SEASON,
        "windowLabel": card.get("window_label") or f"{start.isoformat()}{WINDOW_SEPARATOR}{end.isoformat()}",
        "windowStart": start.isoformat(), "windowEnd": end.isoformat(),
        "notice": " ".join(notices) or None,
        "unitDollars": unit_dollars(),
        "includedMarkets": list(card.get("included_markets") or []),
        "excludedMarkets": list(card.get("excluded_markets") or []),
        "cardSource": card_source, "priceSource": price_source,
        "record": load_record(lab), "teams": teams, "games": games,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the public EPL board feed.")
    ap.add_argument("--lab", default=".")
    ap.add_argument("--out", default="dist/data")
    ap.add_argument("--date", default="")
    args = ap.parse_args(argv)
    today = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    board = build(Path(args.lab).resolve(), today)
    (out / "board.json").write_text(json.dumps(board, indent=1, ensure_ascii=False), encoding="utf-8")
    hist = out / "history"
    hist.mkdir(exist_ok=True)
    frozen = hist / f"{today.isoformat()}.json"
    if not frozen.exists():
        frozen.write_text(json.dumps(board, indent=1, ensure_ascii=False), encoding="utf-8")
    print(
        f"board {today}: {len(board['games'])} fixtures in {board['windowLabel']}, "
        f"card from {board['cardSource']}, prices from {board['priceSource']}. "
        "No odds were fetched, no credit was spent, and no bet is ever placed."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
