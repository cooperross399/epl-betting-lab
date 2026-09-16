"""What the bridges write must be what the readers read.

Three scheduled-task bridges write six files. Four consumers read them: the
browser status page, the run summary, the card notification, and the artifact
list in `.github/workflows/matchday-refresh.yml`. Until this file, that filename
lived as an independent string literal in six places, and every test pinned one
side only:

    tests/test_scheduled_task_bridge.py  asserts the WATCH and SETTLE names the
                                         producer writes — never the card's
    tests/test_browser_status.py         writes a fixture named by the literal,
                                         then asserts the consumer reads it
    tests/test_matchday_refresh.py       compares the workflow's text against a
                                         hardcoded map in the test

Each of those is "the name I just typed equals the name I just typed". Reverting
`CARD_TASK_JSON` alone left all 2275 tests green while `save_soccer_card_task`
wrote `epl_card_task.json` and all four consumers went on reading
`soccer_card_task.json` — the card silently absent from the status page, the run
summary, the notification and the upload.

These tests run the producer and the consumer against the SAME directory, so
neither side can be renamed alone. The repository already reached this
conclusion once, for the delivery issue title: see
`test_the_delivery_title_is_written_in_exactly_one_place`.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epl_betting_lab.config import PROJECT_ROOT
from epl_betting_lab.reports.browser_status import REPORT_FILES, build_status_html
from epl_betting_lab.reports import card_notification
from epl_betting_lab.reports.card_notification import build_notification
from epl_betting_lab.reports.run_summary import build_run_summary
from epl_betting_lab.reports.scheduled_task_bridge import (
    CARD_TASK_JSON,
    CARD_TASK_MARKDOWN,
    SETTLE_TASK_JSON,
    SETTLE_TASK_MARKDOWN,
    WATCH_TASK_JSON,
    WATCH_TASK_MARKDOWN,
    save_soccer_card_task,
    save_soccer_settle_preview_task,
    save_soccer_watch_task,
)

NOW = datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc)


@pytest.fixture
def produced(tmp_path: Path) -> Path:
    """Every bridge run for real, into one directory."""
    save_soccer_watch_task(output_dir=tmp_path, now=NOW)
    save_soccer_card_task(output_dir=tmp_path, now=NOW)
    save_soccer_settle_preview_task(output_dir=tmp_path, now=NOW)
    return tmp_path


# --- the producer side -----------------------------------------------------


@pytest.mark.parametrize(
    "save, expected_json, expected_markdown",
    [
        (save_soccer_watch_task, WATCH_TASK_JSON, WATCH_TASK_MARKDOWN),
        (save_soccer_card_task, CARD_TASK_JSON, CARD_TASK_MARKDOWN),
        (save_soccer_settle_preview_task, SETTLE_TASK_JSON, SETTLE_TASK_MARKDOWN),
    ],
    ids=["watch", "card", "settle"],
)
def test_each_bridge_writes_the_names_it_advertises(
    save, expected_json: str, expected_markdown: str, tmp_path: Path
) -> None:
    """The card had no such assertion; the other two did, which is exactly why
    the card was the one that could drift."""
    result = save(output_dir=tmp_path, now=NOW)

    assert Path(result["json"]).name == expected_json
    assert Path(result["markdown"]).name == expected_markdown
    assert (tmp_path / expected_json).is_file()
    assert (tmp_path / expected_markdown).is_file()


# --- the consumer side, reading what the producer actually wrote -----------


def test_the_status_page_reads_the_files_the_bridges_wrote(produced: Path) -> None:
    """`REPORT_FILES` is the status page's map of what to read. Pointing it at
    a name no bridge writes does not fail — the page renders with the section
    quietly missing."""
    for key in ("model", "card", "settle"):
        assert (produced / REPORT_FILES[key]).is_file(), (
            f"the status page reads {REPORT_FILES[key]!r}, which no bridge wrote"
        )

    html = build_status_html(output_dir=produced, now=NOW)

    assert html.strip()


def test_the_run_summary_reads_the_files_the_bridges_wrote(produced: Path) -> None:
    """A bridge report the summary cannot find is reported as absent, not as an
    error, so a renamed file reads as a run that produced nothing."""
    summary = build_run_summary(output_dir=produced, now=NOW)
    blind = build_run_summary(output_dir=produced / "empty", now=NOW)

    assert summary != blind, (
        "the run summary is identical with and without the bridge reports, so "
        "it is not reading them"
    )


def test_the_notification_reads_the_file_the_card_bridge_wrote(
    produced: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asserted on the path opened, not on the rendered text.

    With no upstream evidence the card bridge writes a *blocked* payload, and a
    notification built from a blocked card is word for word a notification built
    from no card at all — so a differential on the body cannot tell "read it"
    from "could not find it", which is the very confusion this file exists to
    remove. Recording the filename the consumer asks for does tell them apart.
    """
    opened: list[str] = []
    real = card_notification._read

    def recording(path: Path):
        opened.append(Path(path).name)
        return real(path)

    monkeypatch.setattr(card_notification, "_read", recording)
    build_notification(output_dir=produced, now=NOW)

    assert CARD_TASK_JSON in opened, (
        f"the notification read {opened}, none of which is the "
        f"{CARD_TASK_JSON} the card bridge writes"
    )
    assert (produced / CARD_TASK_JSON).is_file()


# --- the one consumer that cannot import the constant ----------------------


def test_the_workflow_uploads_exactly_the_markdown_the_bridges_write() -> None:
    """The artifact list is text in a YAML file: it cannot import a constant,
    so this is the only copy of these names that has to be kept by hand — and
    `if-no-files-found: warn` means a stale path fails silently, uploading
    nothing and saying nothing.

    Asserted against the constants rather than against a literal typed here,
    so renaming the constant without the workflow fails.
    """
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "matchday-refresh.yml"
    ).read_text(encoding="utf-8")
    block = workflow.split("name: matchday-reports", 1)[1].split("if-no-files-found", 1)[0]

    for name in (WATCH_TASK_MARKDOWN, CARD_TASK_MARKDOWN, SETTLE_TASK_MARKDOWN):
        assert f"data/outputs/{name}" in block, (
            f"the bridges write {name}, and the artifact list does not upload it"
        )

    listed = set(re.findall(r"data/outputs/(\S+_task\.md)", block))
    assert listed == {WATCH_TASK_MARKDOWN, CARD_TASK_MARKDOWN, SETTLE_TASK_MARKDOWN}, (
        f"the artifact list uploads task reports nothing writes: "
        f"{sorted(listed - {WATCH_TASK_MARKDOWN, CARD_TASK_MARKDOWN, SETTLE_TASK_MARKDOWN})}"
    )


def test_no_consumer_re_types_a_task_filename() -> None:
    """The literal must appear in one place. Six copies is how the card came to
    be renameable in isolation, and the fix is a shared constant rather than a
    test per copy — a test per copy is what was already there."""
    names = (
        WATCH_TASK_JSON, CARD_TASK_JSON, SETTLE_TASK_JSON,
        WATCH_TASK_MARKDOWN, CARD_TASK_MARKDOWN, SETTLE_TASK_MARKDOWN,
    )
    source = PROJECT_ROOT / "src" / "epl_betting_lab"
    offenders: list[str] = []
    for path in source.rglob("*.py"):
        if path.name == "scheduled_task_bridge.py":
            continue  # where they are defined
        text = path.read_text(encoding="utf-8")
        for name in names:
            if f'"{name}"' in text or f"'{name}'" in text:
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {name}")

    assert not offenders, (
        "these modules re-type a task filename instead of importing the "
        "constant, so the name can be changed in one place and not the other: "
        + ", ".join(offenders)
    )
