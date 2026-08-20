#!/usr/bin/env python
"""Say why the provider step stopped, in one sentence.

The step exits non-zero for two unrelated reasons: the fetch failed, or the
fetch worked and something downstream refused the bundle. Reporting the first
for the second sent a reader looking for a network problem that was not there —
a run stopped by the Thursday cutoff announced that prices could not be
refreshed while 330 rows of freshly fetched prices sat in the bundle.

The reports know the answer between them, so this asks them rather than
guessing. It prints exactly one line and never fails: a run already going wrong
must not also be unable to explain itself.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FALLBACK = (
    "Provider prices could not be refreshed, so the card is built on the last "
    "prices fetched and may be refused as stale."
)

#: A refusal that means the policy worked rather than the system broke.
#:
#: The Thursday cutoff refuses any receipt made after 10:00 New York on a
#: Thursday. Scheduled runs are all before it, so only a run started by hand
#: outside the window meets this — and it is the policy doing its job, not a
#: fault. Reported as a failure it produced a week of red runs and alarming
#: mail, and a health check reasonably concluded the pipeline was broken.
EXPECTED_REFUSALS = ("after the Thursday automation cutoff",)


def is_expected(explanation: str) -> bool:
    """Is this a refusal the system is supposed to make?"""
    return any(phrase in explanation for phrase in EXPECTED_REFUSALS)


def _load(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _blockers(payload: dict) -> list[str]:
    """Blocker sentences, wherever this report happens to keep them."""
    found: list[str] = []
    for value in payload.values():
        if isinstance(value, dict):
            found.extend(_blockers(value))
    for key in ("blockers", "serious_issues"):
        for item in payload.get(key) or []:
            if isinstance(item, str) and item.strip():
                found.append(item.strip())
            elif isinstance(item, dict):
                detail = item.get("detail") or item.get("message") or item.get("issue")
                if detail:
                    found.append(str(detail).strip())
    return found


def explain(outputs: Path) -> str:
    # Order matters: the provider's own verdict first, then the gate that most
    # often refuses a bundle the provider was happy with.
    for name in ("provider_shadow_verification.json", "staging_input_validation.json"):
        blockers = _blockers(_load(outputs / name))
        if blockers:
            # Deduplicate while keeping order; reports repeat themselves.
            seen: list[str] = []
            for blocker in blockers:
                if blocker not in seen:
                    seen.append(blocker)
            return "The provider run was refused: " + " ".join(seen[:3])
    return FALLBACK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/outputs"))
    parser.add_argument(
        "--expected-exit",
        type=int,
        default=0,
        help="Exit with this code when the refusal was an expected one, so a "
        "caller can tell a policy declining from a system breaking.",
    )
    args = parser.parse_args()
    explanation = explain(args.output_dir)
    print(explanation)
    return args.expected_exit if is_expected(explanation) else 0


if __name__ == "__main__":
    raise SystemExit(main())
