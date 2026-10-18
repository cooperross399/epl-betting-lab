#!/usr/bin/env python
"""Measure what being "due" has been worth for Premier League goalscorers.

    PYTHONPATH=src python scripts/run_due_list_backtest.py [--logs CSV]

Fetches every league squad of the seasons asked for from ESPN (keyless, see
`providers.espn_player_logs`), or reads a CSV of the same rows, and asks the
Due List's own `prepare_logs` one question per qualifier appearance: did a
player the rule would have listed score more often than the same qualifiers
did when they were not due?

Writes `data/outputs/due_list_backtest.json` (the headline the card prints)
and `data/outputs/due_list_backtest.md` (the table by band and drought, which
is how the bars were checked). Rates only: historical anytime-goalscorer
prices were never bought, so there is no return figure, and none is implied.

Reads no odds, spends no credit, places no bet.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.due_list import (
    BACKTEST_JSON,
    THRESHOLD,
    TIERS,
    band_label,
    prepare_logs,
    rule_sentence,
)
from epl_betting_lab.providers.espn_player_logs import fetch_logs


#: The first season measured is the second fetched: the first only supplies
#: "last season" for it.
DEFAULT_SEASONS = (2021, 2022, 2023, 2024, 2025)


def _interval(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """Difference of two proportions with a normal-approximation 95% interval."""
    p1, p2 = k1 / n1, k2 / n2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    diff = p1 - p2
    return diff, diff - 1.96 * se, diff + 1.96 * se


def measure(logs: pd.DataFrame) -> dict:
    frame = prepare_logs(logs)
    pool = frame[frame["prior_goals"].fillna(0) >= THRESHOLD]
    if pool.empty:
        raise SystemExit("No qualifier appearances in the logs given.")
    seasons = sorted(pool["season"].unique())
    listed = pool[pool["listed"]]
    others = pool[~pool["listed"]]
    diff, low, high = _interval(
        int(listed["scored"].sum()), len(listed), int(others["scored"].sum()), len(others)
    )
    by_band = []
    for floor, bar in TIERS:
        band = pool[pool["bar"] == bar]
        rows = []
        for drought in range(0, 13):
            cell = band[band["drought"] == drought] if drought < 12 else band[band["drought"] >= 12]
            if len(cell):
                rows.append(
                    {
                        "drought": drought if drought < 12 else "12+",
                        "n": len(cell),
                        "rate": round(float(cell["scored"].mean()), 4),
                        "own_rate": round(float(cell["prior_rate"].mean()), 4),
                    }
                )
        on = band[band["listed"]]
        off = band[~band["listed"]]
        by_band.append(
            {
                "band": band_label(floor),
                "bar": bar,
                "players": int(band["player_id"].nunique()),
                "own_rate": round(float(band["prior_rate"].mean()), 4) if len(band) else None,
                "listed_n": len(on),
                "listed_rate": round(float(on["scored"].mean()), 4) if len(on) else None,
                "others_n": len(off),
                "others_rate": round(float(off["scored"].mean()), 4) if len(off) else None,
                "by_drought": rows,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "ESPN league squads (appearances, totalGoals)",
        "rule": rule_sentence(),
        "hit_rate": {
            "window": f"{seasons[0]}/{str(seasons[0] + 1)[-2:]} to {seasons[-1]}/{str(seasons[-1] + 1)[-2:]}",
            "first_season": int(seasons[0]),
            "last_season": int(seasons[-1]),
            "listed_n": len(listed),
            "listed_rate": round(float(listed["scored"].mean()), 4),
            "listed_own_rate": round(float(listed["prior_rate"].mean()), 4),
            "others_n": len(others),
            "others_rate": round(float(others["scored"].mean()), 4),
            "others_own_rate": round(float(others["prior_rate"].mean()), 4),
            "diff": round(diff, 4),
            "diff_low": round(low, 4),
            "diff_high": round(high, 4),
        },
        "by_band": by_band,
        "priced": None,
        "priced_note": "Historical anytime-goalscorer prices were never bought; no return is measured.",
    }


def render(result: dict) -> str:
    h = result["hit_rate"]
    out = [
        "# Due List backtest (anytime goalscorers)",
        "",
        f"Generated {result['generated_at']} from {result['source']}.",
        "",
        f"Rule: {result['rule']}",
        "",
        "Every appearance by a player who cleared the qualifier last season, split by whether the rule "
        "would have listed him entering it. `own rate` is the share of last season's appearances he "
        "scored in: the rate a player's record alone predicts, which is what \"due\" has to beat.",
        "",
        "| | Appearances | Scored in | Own rate last season |",
        "|:--|--:|--:|--:|",
        f"| Listed (due) | {h['listed_n']:,} | {h['listed_rate']:.1%} | {h['listed_own_rate']:.1%} |",
        f"| Not listed | {h['others_n']:,} | {h['others_rate']:.1%} | {h['others_own_rate']:.1%} |",
        "",
        f"Difference {h['diff']:+.1%} (95% {h['diff_low']:+.1%} to {h['diff_high']:+.1%}), seasons {h['window']}.",
        "",
        result["priced_note"],
        "",
        "## By band and drought",
        "",
    ]
    for band in result["by_band"]:
        out += [
            f"### {band['band']} goals last season (bar {band['bar']}, {band['players']} players)",
            "",
            "| Drought entering | Appearances | Scored in | Own rate |",
            "|:--|--:|--:|--:|",
        ]
        for row in band["by_drought"]:
            out.append(f"| {row['drought']} | {row['n']:,} | {row['rate']:.1%} | {row['own_rate']:.1%} |")
        out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", help="A CSV of ESPN squad rows instead of fetching.")
    parser.add_argument("--seasons", default=",".join(str(s) for s in DEFAULT_SEASONS))
    parser.add_argument("--outputs", default=str(OUTPUTS_DIR))
    args = parser.parse_args(argv)
    if args.logs:
        logs = pd.read_csv(args.logs, dtype={"player_id": str, "event_id": str})
    else:
        seasons = [int(s) for s in args.seasons.split(",") if s.strip()]
        fetched = fetch_logs(seasons)
        if fetched.failed:
            print(f"{len(fetched.failed)} match summaries could not be read and are left out.")
        logs = pd.DataFrame(fetched.rows)
    result = measure(logs)
    outputs = Path(args.outputs)
    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / BACKTEST_JSON).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (outputs / BACKTEST_JSON.replace(".json", ".md")).write_text(render(result), encoding="utf-8")
    print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
