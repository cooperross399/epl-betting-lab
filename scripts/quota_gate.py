#!/usr/bin/env python
"""Exit 0 if a purchase tier may spend, 1 if the quota says shed it.

    python scripts/quota_gate.py extras|snapshot [--shadow PATH]

See `providers/quota_gate.py` for the tiers. Spends nothing.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from epl_betting_lab.providers.quota_gate import (
    FLOORS,
    QUOTA_JSON,
    SHADOW_JSON,
    allowed,
    remaining_credits,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tier", choices=sorted(FLOORS))
    parser.add_argument("--shadow", type=Path, default=None)
    args = parser.parse_args()
    paths = (args.shadow,) if args.shadow else (QUOTA_JSON, SHADOW_JSON)
    remaining = remaining_credits(*paths)
    if allowed(args.tier, *paths):
        print(f"quota {remaining if remaining is not None else 'unknown'}: {args.tier} may spend.")
        return 0
    print(
        f"::warning::quota {remaining} is under the {args.tier} floor of {FLOORS[args.tier]}: "
        f"this purchase is skipped so the main card keeps its prices. Top up the odds quota."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
