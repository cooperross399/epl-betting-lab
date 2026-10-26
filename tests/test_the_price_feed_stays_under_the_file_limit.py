"""The price feed is kept on its branch as one file per day, not one file.

On 2026-10-26 `price_feed.csv` on the `price-feed` branch was 52,491,855
bytes and growing about 1.9 MB a day (17,932 observations on 2026-10-24
alone). GitHub refuses a push carrying any file over 100 MB, so in roughly
four weeks every push to the branch would have been rejected and live
closing-line value, the only fast feedback the card gets, would have stopped
recording.

Compressing the single file would have fitted under the limit and cost more:
git cannot delta one gzip stream against the next, so each of the thirty-odd
pushes a week would add a whole new multi-megabyte blob to the history.
Split by the day an observation was made, a push rewrites only that day's
file, and every earlier day stays the same blob it already was.

Nothing local changes. Every step still restores one
`data/processed/price_feed.csv`, and every Python reader reads it as before.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "price_feed_branch.py"
WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"

HEADER = "observed_at,provider_event_id,date,home_team,away_team,market,selection,book,american_odds\n"


def _row(day: str, book: str = "BetRivers", odds: int = -110) -> str:
    return f"{day}T19:03:49+00:00,082f74fe6a8b,2026-11-01,Sunderland,Arsenal,1x2,away,{book},{odds}\n"


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    done = subprocess.run(
        ["git", *args], cwd=repo, input=stdin, capture_output=True, text=True, check=True
    )
    return done.stdout


def _helper(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=repo, capture_output=True, text=True
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    return tmp_path


def _publish(repo: Path, *paths: Path) -> str:
    """What a writer does: one shard tree per feed, committed as the branch tip."""
    lines = []
    for path in paths:
        done = _helper(repo, "entry", str(path))
        assert done.returncode == 0, done.stderr
        lines.append(done.stdout.strip())
    tree = _git(repo, "mktree", stdin="\n".join(lines) + "\n").strip()
    return _tip(repo, tree)


def _tip(repo: Path, tree: str) -> str:
    commit = _git(repo, "-c", "user.name=t", "-c", "user.email=t@t",
                  "commit-tree", tree, "-m", "prices").strip()
    _git(repo, "update-ref", "refs/price-feed-tip", commit)
    return commit


def test_the_feed_comes_back_exactly_as_it_was_written(repo: Path) -> None:
    feed = repo / "price_feed.csv"
    feed.write_text(HEADER + _row("2026-10-24") + _row("2026-10-24", "Bovada") + _row("2026-10-25"))
    _publish(repo, feed)

    shown = _helper(repo, "show", "refs/price-feed-tip", "price_feed.csv")
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout == feed.read_text()


def test_each_day_is_its_own_file_on_the_branch(repo: Path) -> None:
    feed = repo / "price_feed.csv"
    feed.write_text(HEADER + _row("2026-10-24") + _row("2026-10-25"))
    _publish(repo, feed)

    names = _git(repo, "ls-tree", "-r", "--name-only", "refs/price-feed-tip").split()
    assert names == ["price_feed/2026-10-24.csv", "price_feed/2026-10-25.csv"]
    # Every shard carries the header, so each one reads on its own.
    first = _git(repo, "show", "refs/price-feed-tip:price_feed/2026-10-24.csv")
    assert first == HEADER + _row("2026-10-24")


def test_a_new_day_leaves_every_earlier_day_the_same_blob(repo: Path) -> None:
    """The reason this is not one compressed file: history grows by a day, not a feed."""
    feed = repo / "price_feed.csv"
    feed.write_text(HEADER + _row("2026-10-24") + _row("2026-10-25"))
    _publish(repo, feed)
    before = _git(repo, "rev-parse", "refs/price-feed-tip:price_feed/2026-10-24.csv")

    feed.write_text(feed.read_text() + _row("2026-10-26"))
    _publish(repo, feed)
    after = _git(repo, "rev-parse", "refs/price-feed-tip:price_feed/2026-10-24.csv")
    assert before == after


def test_publishing_the_same_feed_twice_builds_the_same_tree(repo: Path) -> None:
    """The writers skip a push when the tree is unchanged; that needs a stable tree."""
    feed = repo / "price_feed.csv"
    feed.write_text(HEADER + _row("2026-10-24") + _row("2026-10-25"))
    first = _helper(repo, "entry", str(feed)).stdout
    second = _helper(repo, "entry", str(feed)).stdout
    assert first == second and first.startswith("040000 tree ")
    assert first.rstrip("\n").endswith("\tprice_feed")


def test_a_row_without_a_usable_time_is_kept_not_dropped(repo: Path) -> None:
    feed = repo / "price_feed.csv"
    feed.write_text(HEADER + _row("2026-10-24") + ",abc,2026-11-01,A,B,1x2,home,Bovada,100\n")
    _publish(repo, feed)
    shown = _helper(repo, "show", "refs/price-feed-tip", "price_feed.csv").stdout
    assert shown.count("\n") == 3


def test_the_day_is_read_from_the_observed_at_column_wherever_it_sits(repo: Path) -> None:
    """The extra competitions' feed starts with `competition,commence_time`."""
    feed = repo / "price_feed_extra.csv"
    feed.write_text(
        "competition,commence_time," + HEADER
        + ",," + _row("2026-10-24")
        + "UCL,2026-10-28T20:00:00Z," + _row("2026-10-25")
    )
    _publish(repo, feed)
    names = _git(repo, "ls-tree", "-r", "--name-only", "refs/price-feed-tip").split()
    assert names == ["price_feed_extra/2026-10-24.csv", "price_feed_extra/2026-10-25.csv"]
    shown = _helper(repo, "show", "refs/price-feed-tip", "price_feed_extra.csv").stdout
    assert shown == feed.read_text()


def test_an_old_tip_with_the_single_file_still_restores(repo: Path) -> None:
    """The first run after this change reads the branch as it is today."""
    blob = _git(repo, "hash-object", "-w", "--stdin", stdin=HEADER + _row("2026-10-24")).strip()
    tree = _git(repo, "mktree", stdin=f"100644 blob {blob}\tprice_feed.csv\n").strip()
    _tip(repo, tree)

    shown = _helper(repo, "show", "refs/price-feed-tip", "price_feed.csv")
    assert shown.returncode == 0
    assert shown.stdout == HEADER + _row("2026-10-24")


def test_a_feed_the_branch_does_not_hold_is_an_error_not_an_empty_file(repo: Path) -> None:
    feed = repo / "price_feed.csv"
    feed.write_text(HEADER + _row("2026-10-24"))
    _publish(repo, feed)
    missing = _helper(repo, "show", "refs/price-feed-tip", "price_feed_extra.csv")
    assert missing.returncode != 0 and missing.stdout == ""


def _step(workflow: str, name: str) -> str:
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    return text.split(f"- name: {name}", 1)[1].split("\n      - name:", 1)[0]


def _code(block: str) -> str:
    return "\n".join(l for l in block.splitlines() if not l.strip().startswith("#"))


WRITERS = [
    ("matchday-refresh.yml", "Record this run's prices in the price feed"),
    ("closing-snapshot.yml", "Append the observation to the price feed"),
]
READERS = [
    ("matchday-refresh.yml", "Restore the price feed before anything reads it"),
    ("closing-snapshot.yml", "Restore the price feeds before collecting into them"),
    ("publish-board.yml", "Read the price feed for open prices and line movement"),
] + WRITERS


@pytest.mark.parametrize("workflow,step", WRITERS)
def test_no_writer_puts_a_whole_feed_in_one_blob(workflow: str, step: str) -> None:
    code = _code(_step(workflow, step))
    assert "git hash-object" not in code
    assert "scripts/price_feed_branch.py entry" in code


@pytest.mark.parametrize("workflow,step", WRITERS)
def test_the_writers_retire_the_single_file(workflow: str, step: str) -> None:
    """Left on the branch, the old 52 MB file would keep growing nowhere and
    sit beside the shards looking like a second feed."""
    replacing = _code(_step(workflow, step)).split("REPLACING=", 1)[1].split("\n", 1)[0]
    names = replacing.strip('"').split("|")
    assert "price_feed.csv" in names and "price_feed" in names


@pytest.mark.parametrize("workflow,step", READERS)
def test_every_reader_understands_the_shards(workflow: str, step: str) -> None:
    code = _code(_step(workflow, step))
    for line in code.splitlines():
        assert not ("git show" in line and "price_feed" in line), line
    if (workflow, step) != WRITERS[1]:
        assert "scripts/price_feed_branch.py show" in code


def test_the_shrink_guard_counts_the_sharded_parent() -> None:
    code = _code(_step(*WRITERS[1]))
    assert 'scripts/price_feed_branch.py show "$PARENT" "$FEED"' in code
