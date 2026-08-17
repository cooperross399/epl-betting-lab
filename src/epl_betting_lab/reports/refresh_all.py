"""Refresh every report in dependency order, in one step.

Regenerating the picture took five commands run in the right sequence. Getting
the order wrong produces a status page built from a stale card, which is worse
than no page at all because it looks current. Encoding the order once removes
both the tedium and that failure mode.

Deliberately offline: it re-derives reports from evidence already on disk. It
never contacts the provider, so it cannot spend quota or change what the
evidence says. Refreshing the view and refetching the data are different
actions and stay separate.

A failing step does not abort the run. Later steps are attempted and the
failure is reported, because a status page missing one section is more useful
than no output plus a traceback.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from epl_betting_lab.config import OUTPUTS_DIR


REFRESH_JSON_FILENAME = "refresh_all_reports.json"


def _steps() -> list[tuple[str, str, Callable[[Path], Any]]]:
    """Steps in dependency order: each reads what the previous produced."""
    from epl_betting_lab.reports.automated_card import save_automated_card
    from epl_betting_lab.reports.automated_card_input import (
        save_automated_card_input,
    )
    from epl_betting_lab.reports.browser_status import save_status_html
    from epl_betting_lab.reports.card_history import (
        archive_card,
        save_card_comparison,
    )
    from epl_betting_lab.reports.scheduled_task_bridge import (
        save_epl_card_task,
        save_epl_model_task,
        save_epl_settle_preview_task,
    )

    return [
        (
            "card_input",
            "Derive the card input from provider staging evidence",
            lambda outputs: save_automated_card_input(output_dir=outputs),
        ),
        (
            "automated_card",
            "Generate the card from eligible markets",
            lambda outputs: save_automated_card(output_dir=outputs),
        ),
        (
            "archive_card",
            "Archive this card run",
            lambda outputs: archive_card(output_dir=outputs),
        ),
        (
            "card_comparison",
            "Compare the two most recent card runs",
            lambda outputs: save_card_comparison(output_dir=outputs),
        ),
        (
            "epl_model_task",
            "Refresh the EPL Model routine report",
            lambda outputs: save_epl_model_task(output_dir=outputs),
        ),
        (
            "epl_card_task",
            "Refresh the EPL CARD routine report",
            lambda outputs: save_epl_card_task(output_dir=outputs),
        ),
        (
            "epl_settle_preview_task",
            "Refresh the EPL SETTLE preview report",
            lambda outputs: save_epl_settle_preview_task(output_dir=outputs),
        ),
        (
            "status_page",
            "Render the browser status page",
            lambda outputs: save_status_html(output_dir=outputs),
        ),
    ]


def refresh_all_reports(
    *,
    output_dir: Path | None = None,
    only: Sequence[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run every refresh step, reporting each outcome."""
    outputs = OUTPUTS_DIR if output_dir is None else Path(output_dir)
    outputs.mkdir(parents=True, exist_ok=True)
    selected = set(only) if only else None

    results: list[dict[str, Any]] = []
    for name, description, run in _steps():
        if selected is not None and name not in selected:
            results.append(
                {"step": name, "description": description, "status": "skipped"}
            )
            continue
        try:
            run(outputs)
        except Exception as exc:  # a broken step must not hide the others
            results.append(
                {
                    "step": name,
                    "description": description,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }
            )
        else:
            results.append(
                {"step": name, "description": description, "status": "ok"}
            )

    failed = [item for item in results if item["status"] == "failed"]
    summary = {
        "report": "Refresh All Reports",
        "generated_at": (now or datetime.now(timezone.utc))
        .astimezone(timezone.utc)
        .isoformat(timespec="seconds"),
        "steps": results,
        "ok_count": sum(1 for item in results if item["status"] == "ok"),
        "failed_count": len(failed),
        "skipped_count": sum(1 for item in results if item["status"] == "skipped"),
        "all_ok": not failed,
        "safety": {
            "provider_contacted": False,
            "quota_spent": False,
            "picks_published": False,
            "bets_placed": False,
            "settlement_applied": False,
            "protected_files_written": False,
        },
    }
    (outputs / REFRESH_JSON_FILENAME).write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return summary
