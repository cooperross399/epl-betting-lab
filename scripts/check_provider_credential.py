#!/usr/bin/env python
"""Check that the provider credential authenticates, without revealing it.

Asks the sports-list endpoint, which costs no quota, and reports only whether
the provider accepted the credential. The key is never printed, written,
logged, or compared. Its length is reported so an operator can distinguish
"empty" from "present" without learning any of it.

Reads the key from the environment, which is where a GitHub Actions secret and
a gitignored local `.env` both arrive. Never fetches odds, generates picks,
places bets, applies settlement, or enables cron.
"""

from __future__ import annotations

import argparse
import os

from epl_betting_lab.providers.credential_check import (
    check_provider_credential,
    render_credential_check,
)
from epl_betting_lab.providers.env_file import load_provider_env
from epl_betting_lab.providers.odds_api_staging_provider import DEFAULT_API_BASE_URL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-env-file",
        action="store_true",
        help="Do not consult a local .env; use the process environment only.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EPL_ODDS_API_BASE_URL", DEFAULT_API_BASE_URL),
        help="Provider base URL. Must be an approved HTTPS host.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("EPL Betting Lab - Provider Credential Check")
    print(
        "Reports only whether the provider accepted the credential. The key is "
        "never printed, written, logged, or compared. Quota cost: 0."
    )

    if not args.no_env_file:
        load_result = load_provider_env()
        print(load_result.summary_line())
        for warning in load_result.warnings:
            print(f"WARNING: {warning}")

    report = check_provider_credential(os.environ, base_url=args.base_url)
    for line in render_credential_check(report):
        print(line)

    if not report["credential_present"]:
        return 2
    return 0 if report["authenticated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
