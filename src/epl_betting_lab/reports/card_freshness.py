"""Did any selection on this card kick off before the card was generated?

The 2026-09-28 card carried eight fixtures that had already been played, three
of them twelve days finished. Two gates now stop that — `automated_card`'s
kickoff quarantine for the Premier League, and `extra_competitions_card`'s
`gate_slate` for everything else.

This asks the question they are supposed to have answered, from the other
direction. It does not read either gate's count of what it dropped: a gate that
is broken reports dropping nothing, which is indistinguishable from a gate with
nothing to drop. It reads the selections that SHIPPED and checks their kickoffs
against the moment the card was written. The answer should always be zero, and
zero means something only because it is computed from the output rather than
from the mechanism's own opinion of itself.

`unchecked` is reported beside it and is not a pass. A selection with no kickoff
recorded cannot be confirmed either way, and a card whose selections are all
unchecked would otherwise report a clean zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

#: Where each card writes what it recommended.
CARD_JSON = "automated_card.json"
EXTRA_CARD_JSON = "extra_competitions_card.json"

#: Sections of the Premier League card that are recommendations. `quarantined`
#: and `already_started` are deliberately excluded: those are the rows a gate
#: withheld, and finding a started fixture there is the gate working.
PLAYABLE_SECTIONS = ("best_bets", "leans")


@dataclass(frozen=True)
class Fault:
    section: str
    fixture: str
    market: str
    selection: str
    kickoff: str
    generated_at: str


@dataclass(frozen=True)
class FreshnessVerdict:
    checked: int = 0
    unchecked: int = 0
    faults: list[Fault] = field(default_factory=list)
    sections: dict[str, int] = field(default_factory=dict)
    generated_at: str | None = None
    read: list[str] = field(default_factory=list)

    @property
    def fault_count(self) -> int:
        return len(self.faults)

    @property
    def clean(self) -> bool:
        """No selection shipped after its own kickoff.

        Silent on `unchecked` on purpose: that is a separate fact and hiding it
        inside a boolean is how "nothing detected" comes to read as "nothing
        wrong".
        """
        return not self.faults

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "unchecked": self.unchecked,
            "faults": self.fault_count,
            "clean": self.clean,
            "sections": dict(self.sections),
            "generated_at": self.generated_at,
            "read": list(self.read),
            "detail": [
                {
                    "section": fault.section,
                    "fixture": fault.fixture,
                    "market": fault.market,
                    "selection": fault.selection,
                    "kickoff": fault.kickoff,
                    "generated_at": fault.generated_at,
                }
                for fault in self.faults
            ],
        }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _stamp(value: object) -> pd.Timestamp | None:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return None if pd.isna(parsed) else parsed


def _audit(
    rows: Sequence[Mapping[str, Any]],
    *,
    section: str,
    generated_at: pd.Timestamp,
) -> tuple[int, int, list[Fault]]:
    checked = 0
    unchecked = 0
    faults: list[Fault] = []
    for row in rows:
        kickoff = _stamp(row.get("kickoff_time") or row.get("commence_time"))
        if kickoff is None:
            unchecked += 1
            continue
        checked += 1
        if kickoff <= generated_at:
            faults.append(
                Fault(
                    section=section,
                    fixture=f"{row.get('home_team')} v {row.get('away_team')}",
                    market=str(row.get("market")),
                    selection=str(row.get("selection")),
                    kickoff=kickoff.isoformat(),
                    generated_at=generated_at.isoformat(),
                )
            )
    return checked, unchecked, faults


def audit_card_freshness(*, output_dir: Path) -> FreshnessVerdict:
    """Check every shipped selection against the time its card was written."""
    outputs = Path(output_dir)
    card = _read_json(outputs / CARD_JSON)
    extra = _read_json(outputs / EXTRA_CARD_JSON)
    read = [name for name, payload in ((CARD_JSON, card), (EXTRA_CARD_JSON, extra)) if payload]

    checked = 0
    unchecked = 0
    faults: list[Fault] = []
    sections: dict[str, int] = {}

    generated = _stamp(card.get("generated_at"))
    if card and generated is not None:
        for name in PLAYABLE_SECTIONS:
            rows = card.get(name) or []
            if not isinstance(rows, list):
                continue
            got, missing, found = _audit(rows, section=name, generated_at=generated)
            checked += got
            unchecked += missing
            faults.extend(found)
            sections[name] = len(found)
    elif card:
        # A card with no generation time cannot be audited at all, and saying
        # so is the point: every row counts as unchecked rather than clean.
        for name in PLAYABLE_SECTIONS:
            unchecked += len(card.get(name) or [])

    extra_generated = _stamp(extra.get("generated_at"))
    extra_rows = extra.get("selections") or []
    if extra and extra_generated is not None and isinstance(extra_rows, list):
        by_competition: dict[str, list[Mapping[str, Any]]] = {}
        for row in extra_rows:
            by_competition.setdefault(str(row.get("competition", "?")), []).append(row)
        for competition, rows in sorted(by_competition.items()):
            got, missing, found = _audit(
                rows, section=competition, generated_at=extra_generated
            )
            checked += got
            unchecked += missing
            faults.extend(found)
            sections[competition] = len(found)
    elif extra:
        unchecked += len(extra_rows) if isinstance(extra_rows, list) else 0

    return FreshnessVerdict(
        checked=checked,
        unchecked=unchecked,
        faults=faults,
        sections=sections,
        generated_at=generated.isoformat() if generated is not None else None,
        read=read,
    )


def render_freshness(verdict: FreshnessVerdict) -> list[str]:
    """Lines for the run summary and the card."""
    if not verdict.read:
        return ["Freshness: no card to check."]
    lines = [
        f"Freshness: {verdict.fault_count} selection(s) kicked off at or before "
        f"the card was generated, of {verdict.checked} checked."
    ]
    if verdict.unchecked:
        lines.append(
            f"  {verdict.unchecked} selection(s) carried no kickoff and could "
            "not be checked either way."
        )
    for fault in verdict.faults:
        lines.append(
            f"  STALE {fault.section}: {fault.fixture} {fault.market} "
            f"{fault.selection} kicked off {fault.kickoff}, card generated "
            f"{fault.generated_at}."
        )
    return lines
