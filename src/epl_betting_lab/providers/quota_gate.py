"""Shed the extra purchases before the quota runs out, main card last.

On 2026-10-10 the odds quota reached zero and every run after it was degraded:
no prices for anything, the Premier League card included. The NHL lab caps
its spend in code (its "credit cap that could not hold, and now does"). Here
the purchases are ranked:

- ``extras``: the props refresh and the cup / European / Championship price
  collection. Shed below `SHED_EXTRAS_BELOW`.
- ``snapshot``: the Closing Snapshot's near-kick-off purchase (about 500 a
  firing). Shed below `CARD_RESERVE`, so what is left buys the matchday card
  (about 122 a run).

The reading comes from the free credential check that runs first in both
workflows (`provider_quota.json`), else this run's price fetch
(`provider_shadow_verification.json`). An unknown quota sheds nothing: a
missing reading is not a low one.
"""

from __future__ import annotations

import json
from pathlib import Path

from epl_betting_lab.config import OUTPUTS_DIR

#: About three days of the observed burn (`request_budget`, 3,600 a day).
SHED_EXTRAS_BELOW = 10_000
#: About twenty matchday runs at 122 each, with room for a bad estimate.
CARD_RESERVE = 3_000

QUOTA_JSON = OUTPUTS_DIR / "provider_quota.json"
SHADOW_JSON = OUTPUTS_DIR / "provider_shadow_verification.json"

FLOORS = {"extras": SHED_EXTRAS_BELOW, "snapshot": CARD_RESERVE}


def _read(path: Path) -> int | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    quota = data.get("api_quota", data) if isinstance(data, dict) else {}
    raw = quota.get("requests_remaining") if isinstance(quota, dict) else None
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


def remaining_credits(*paths: Path) -> int | None:
    for path in paths or (QUOTA_JSON, SHADOW_JSON):
        value = _read(path)
        if value is not None:
            return value
    return None


def allowed(tier: str, *paths: Path) -> bool:
    remaining = remaining_credits(*paths)
    return remaining is None or remaining >= FLOORS[tier]
