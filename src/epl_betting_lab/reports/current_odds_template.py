from __future__ import annotations

from pathlib import Path

import pandas as pd

from epl_betting_lab.config import MANUAL_DIR


CURRENT_ODDS_COLUMNS = [
    "date",
    "home_team",
    "away_team",
    "market",
    "selection",
    "american_odds",
    "closing_american_odds",
    "book",
    "notes",
]

SUPPORTED_MARKETS = [
    ("1x2", "home"),
    ("1x2", "draw"),
    ("1x2", "away"),
    ("total_2_5", "over"),
    ("total_2_5", "under"),
    ("btts", "yes"),
    ("btts", "no"),
]


def _selection_note(market: str, selection: str) -> str:
    base = "Enter real sportsbook odds. Avoid heavy juice worse than about -160 unless the model clearly supports it."
    if market == "total_2_5" and selection == "under":
        return f"High caution: totals unders have been a model leak. {base}"
    return base


def _filter_week(fixtures: pd.DataFrame, week: str | int | None) -> pd.DataFrame:
    if week is None:
        return fixtures
    for column in ["matchweek", "week"]:
        if column in fixtures.columns:
            return fixtures[fixtures[column].astype(str) == str(week)].copy()
    return fixtures


def build_current_odds_template(fixtures: pd.DataFrame, book: str = "", week: str | int | None = None) -> pd.DataFrame:
    fixtures = _filter_week(fixtures.copy(), week)
    rows: list[dict[str, object]] = []
    for _, fixture in fixtures.iterrows():
        for market, selection in SUPPORTED_MARKETS:
            rows.append({
                "date": fixture.get("date", ""),
                "home_team": fixture.get("home_team", ""),
                "away_team": fixture.get("away_team", ""),
                "market": market,
                "selection": selection,
                "american_odds": "",
                "closing_american_odds": "",
                "book": book,
                "notes": _selection_note(market, selection),
            })
    return pd.DataFrame(rows, columns=CURRENT_ODDS_COLUMNS)


def current_odds_template_next_steps(path: Path, week: str | int | None = None) -> str:
    week_note = "" if week is None else f" for week/matchweek {week}"
    return "\n".join([
        f"Created `{path}`{week_note}.",
        "",
        "Next steps:",
        "1. Fill in `american_odds` with real sportsbook prices.",
        "2. Fill in `book` if it is blank.",
        "3. Leave `closing_american_odds` blank until after the market closes.",
        "4. Run `python scripts/validate_current_odds.py`.",
        "5. Generate Thursday best bets from the dashboard or with `python scripts/generate_thursday_best_bets.py`.",
    ])


def create_current_odds_template(
    fixtures: pd.DataFrame,
    output_path: Path | None = None,
    *,
    overwrite: bool = False,
    book: str = "",
    week: str | int | None = None,
) -> tuple[Path, pd.DataFrame, str]:
    output_path = output_path or MANUAL_DIR / "current_odds.csv"
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"`{output_path}` already exists. The template helper did not overwrite it. "
            "Use `python scripts/create_current_odds_template.py --overwrite` only when you intentionally want to replace it."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    template = build_current_odds_template(fixtures, book=book, week=week)
    template.to_csv(output_path, index=False)
    return output_path, template, current_odds_template_next_steps(output_path, week=week)
