#!/usr/bin/env python
"""Write the card notification and say whether it should be sent.

Prints `post` or `skip` on stdout so the workflow can branch, and writes the
comment body to --out. Deciding here rather than in shell keeps the rule
testable: a run emails only when the selections changed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.reports.card_notification import ISSUE_TITLE, build_notification


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Where to write the comment body")
    parser.add_argument("--run-url", default="", help="Link back to the run")
    parser.add_argument(
        "--title-out",
        help="Write the delivery issue title here, so the workflow and this "
        "module cannot disagree about which issue to post to",
    )
    args = parser.parse_args()

    result = build_notification(run_url=args.run_url)
    Path(args.out).write_text(result["body"], encoding="utf-8")
    if args.title_out:
        Path(args.title_out).write_text(ISSUE_TITLE, encoding="utf-8")
    print(result["reason"], flush=True)
    print("post" if result["should_post"] else "skip")


if __name__ == "__main__":
    main()
