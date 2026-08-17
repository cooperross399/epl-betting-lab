"""Archive each automated card and compare consecutive runs.

A card regenerated on Thursday and again on Friday can differ for two very
different reasons: the model changed its mind, or the market moved. Without a
record of the previous run, both look identical — the card simply says something
new and nothing explains why.

This archives every generated card and diffs the latest two, reporting which
selections appeared, which disappeared, and which survived at a different price.
Price movement is reported alongside, so a pick that merely got worse is
distinguishable from a pick that was dropped.

Read-only with respect to everything else: it archives and compares, and never
regenerates a card, contacts a provider, edits a protected file, or turns a
comparison into a recommendation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from epl_betting_lab.config import OUTPUTS_DIR


CARD_JSON_FILENAME = "automated_card.json"
ARCHIVE_ROOT = Path("archive") / "automated_cards"
COMPARISON_JSON_FILENAME = "automated_card_comparison.json"
COMPARISON_MARKDOWN_FILENAME = "automated_card_comparison.md"

#: Sections compared. Passes are included because a pick moving from best bet to
#: pass is exactly the kind of change worth noticing.
SECTIONS = ("best_bets", "leans", "passes_or_avoids")


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _selection_key(row: Mapping[str, Any]) -> str:
    """Identity of a selection, independent of price or section."""
    return "|".join(
        _clean(row.get(field)).casefold()
        for field in ("home_team", "away_team", "market", "selection")
    )


def _label(row: Mapping[str, Any]) -> str:
    return (
        f"{_clean(row.get('home_team'))} v {_clean(row.get('away_team'))} "
        f"{_clean(row.get('market'))} {_clean(row.get('selection'))}"
    )


def _price(row: Mapping[str, Any]) -> float | None:
    try:
        return float(row.get("american_odds"))
    except (TypeError, ValueError):
        return None


def _index(card: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Every selection in the card, keyed by identity, tagged with its section."""
    found: dict[str, dict[str, Any]] = {}
    for section in SECTIONS:
        rows = card.get(section)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            key = _selection_key(row)
            if not key.strip("|"):
                continue
            found[key] = {
                "section": section,
                "label": _label(row),
                "market": _clean(row.get("market")),
                "selection": _clean(row.get("selection")),
                "american_odds": _price(row),
                "book": _clean(row.get("book")),
                "confidence_tier": _clean(row.get("confidence_tier")),
            }
    return found


def archive_card(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Copy the current card into a timestamped archive directory."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    card = _read_json(outputs / CARD_JSON_FILENAME)
    if not card:
        return {"archived": False, "reason": "No automated card report to archive."}

    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    directory = (
        outputs / ARCHIVE_ROOT / moment.strftime("%Y-%m-%d") / moment.strftime("%H%M%S")
    )
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / CARD_JSON_FILENAME
    target.write_text(
        json.dumps(card, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    try:
        display = target.relative_to(outputs).as_posix()
    except ValueError:
        display = str(target)
    return {"archived": True, "path": display, "generated_at": _clean(card.get("generated_at"))}


def _archived_cards(outputs: Path) -> list[tuple[str, dict[str, Any]]]:
    """Archived cards, newest first, keyed by their directory path."""
    root = outputs / ARCHIVE_ROOT
    if not root.is_dir():
        return []
    found: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(root.glob("*/*/" + CARD_JSON_FILENAME), reverse=True):
        payload = _read_json(path)
        if payload:
            try:
                display = path.relative_to(outputs).as_posix()
            except ValueError:
                display = str(path)
            found.append((display, payload))
    return found


def build_card_comparison(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compare the two most recent archived cards."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    archived = _archived_cards(outputs)
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    summary: dict[str, Any] = {
        "report": "Automated Card Comparison",
        "generated_at": moment.isoformat(timespec="seconds"),
        "archived_card_count": len(archived),
        "latest_path": "",
        "previous_path": "",
        "comparable": False,
        "added": [],
        "removed": [],
        "moved_section": [],
        "price_changed": [],
        "unchanged_count": 0,
        "notes": [],
        "safety": {
            "card_regenerated": False,
            "provider_contacted": False,
            "recommendation_made": False,
        },
    }

    if len(archived) < 2:
        summary["notes"].append(
            "At least two archived cards are required for a comparison; "
            f"{len(archived)} found."
        )
        return summary

    latest_path, latest = archived[0]
    previous_path, previous = archived[1]
    summary.update(
        {
            "latest_path": latest_path,
            "previous_path": previous_path,
            "comparable": True,
        }
    )

    new_index = _index(latest)
    old_index = _index(previous)

    for key in sorted(set(new_index) - set(old_index)):
        summary["added"].append({**new_index[key], "key": key})
    for key in sorted(set(old_index) - set(new_index)):
        summary["removed"].append({**old_index[key], "key": key})

    unchanged = 0
    for key in sorted(set(new_index) & set(old_index)):
        new_row, old_row = new_index[key], old_index[key]
        changed = False
        if new_row["section"] != old_row["section"]:
            summary["moved_section"].append(
                {
                    "key": key,
                    "label": new_row["label"],
                    "from_section": old_row["section"],
                    "to_section": new_row["section"],
                }
            )
            changed = True
        if (
            new_row["american_odds"] is not None
            and old_row["american_odds"] is not None
            and new_row["american_odds"] != old_row["american_odds"]
        ):
            summary["price_changed"].append(
                {
                    "key": key,
                    "label": new_row["label"],
                    "from_price": old_row["american_odds"],
                    "to_price": new_row["american_odds"],
                    "from_book": old_row["book"],
                    "to_book": new_row["book"],
                }
            )
            changed = True
        if not changed:
            unchanged += 1
    summary["unchanged_count"] = unchanged

    if not any(
        summary[key] for key in ("added", "removed", "moved_section", "price_changed")
    ):
        summary["notes"].append("The two most recent cards are identical.")
    return summary


def render_card_comparison(summary: Mapping[str, Any]) -> str:
    lines = [
        "# Automated Card Comparison",
        "",
        (
            "What changed between the two most recent card runs. A selection can "
            "change because the model changed its mind or because the market "
            "moved; price movement is reported separately so the two are not "
            "confused."
        ),
        "",
        f"- Archived cards: **{summary['archived_card_count']}**",
        f"- Latest: `{summary['latest_path'] or 'none'}`",
        f"- Previous: `{summary['previous_path'] or 'none'}`",
        f"- Unchanged selections: **{summary['unchanged_count']}**",
        "",
    ]
    if not summary["comparable"]:
        lines.extend(["## Not comparable", ""])
        lines.extend(f"- {item}" for item in summary["notes"])
        lines.append("")
        return "\n".join(lines)

    def _section(title: str, rows: Sequence[Mapping[str, Any]], render) -> list[str]:
        if not rows:
            return [f"## {title}", "", "_None._", ""]
        return [f"## {title}", "", *[f"- {render(row)}" for row in rows], ""]

    lines.extend(
        _section(
            "Added",
            summary["added"],
            lambda r: f"{r['label']} ({r['section']}) at {r['american_odds']} @ {r['book'] or 'unknown book'}",
        )
    )
    lines.extend(
        _section(
            "Removed",
            summary["removed"],
            lambda r: f"{r['label']} (was {r['section']})",
        )
    )
    lines.extend(
        _section(
            "Moved section",
            summary["moved_section"],
            lambda r: f"{r['label']}: {r['from_section']} → {r['to_section']}",
        )
    )
    lines.extend(
        _section(
            "Price changed",
            summary["price_changed"],
            lambda r: (
                f"{r['label']}: {r['from_price']} → {r['to_price']}"
                + (
                    f" (book {r['from_book']} → {r['to_book']})"
                    if r["from_book"] != r["to_book"]
                    else ""
                )
            ),
        )
    )
    if summary["notes"]:
        lines.extend(["## Notes", "", *[f"- {item}" for item in summary["notes"]], ""])
    lines.extend(
        [
            "## Safety",
            "",
            "- Card regenerated: **No**",
            "- Provider contacted: **No**",
            "- Recommendation made: **No** (this reports change, not value)",
            "",
        ]
    )
    return "\n".join(lines)


def save_card_comparison(
    *,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    summary = build_card_comparison(output_dir=outputs, now=now)
    outputs.mkdir(parents=True, exist_ok=True)
    json_path = outputs / COMPARISON_JSON_FILENAME
    markdown_path = outputs / COMPARISON_MARKDOWN_FILENAME
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(render_card_comparison(summary), encoding="utf-8")
    return {"summary": summary, "json": str(json_path), "markdown": str(markdown_path)}
