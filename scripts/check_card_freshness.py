#!/usr/bin/env python
"""Check that no selection on the card kicked off before the card was written.

Asks, from the output side, the question the two kickoff gates are supposed to
have answered. It does not read either gate's count of what it dropped: a broken
gate reports dropping nothing, which is indistinguishable from a gate with
nothing to drop.

Read only with respect to everything else. Writes one report, and exits non-zero
if a stale selection shipped so a run cannot pass that quietly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from epl_betting_lab.config import OUTPUTS_DIR
from epl_betting_lab.reports.card_freshness import (
    audit_card_freshness,
    render_freshness,
)

REPORT_FILENAME = "card_freshness.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero when a selection carries no kickoff. Off by default: "
            "records written before kickoffs were captured have none and never "
            "will, and failing every run over history nobody can change trains "
            "the reader to ignore the check."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = OUTPUTS_DIR if args.output_dir is None else args.output_dir
    verdict = audit_card_freshness(output_dir=outputs)

    outputs.mkdir(parents=True, exist_ok=True)
    (outputs / REPORT_FILENAME).write_text(
        json.dumps(verdict.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print("EPL Betting Lab - Card Freshness")
    for line in render_freshness(verdict):
        print(line)
    if not verdict.read:
        # Nothing to check is neither a pass nor a failure: the card build is
        # what would have failed, and it reports that itself.
        return 0
    if verdict.faults:
        return 1
    if args.strict and verdict.unchecked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
