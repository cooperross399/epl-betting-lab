"""The shared pages are the pinned tag of cooperross399/betting-lab-shared.

Board, Results, Archive and Graphic (.dc.html), lib/live.js, lib/format.js,
lib/sports.js and this lab's team logos are one set of files across the NHL,
EPL and CBB labs, with every lab-only feature gated on the sport key. They live
in the shared repository, and `web/shared.lock.json` pins one tag of it with
the SHA-256 of every file this lab takes. The publish run copies that tag in
(`web/sync_shared.py --from`) and fails on a byte that differs from the lock;
these hold the committed copies to the same lock, so the suite needs no network
and a copy edited here and not in the shared repository is a red build.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def _sync():
    spec = importlib.util.spec_from_file_location("sync_shared", WEB / "sync_shared.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_lock_pins_a_tag_of_the_shared_repository() -> None:
    lock = _sync().load_lock()
    assert lock["repo"] == "cooperross399/betting-lab-shared"
    assert lock["tag"].startswith("v") and lock["sport"] in ("nhl", "epl", "cbb")


def test_the_lock_names_every_shared_page_and_every_logo() -> None:
    sync = _sync()
    names = set(sync.load_lock()["files"])
    assert set(sync.PAGES) <= names
    on_disk = {f"logos/{p.name}" for p in (WEB / "logos").iterdir() if p.is_file()}
    assert {n for n in names if n.startswith("logos/")} == on_disk


def test_each_committed_copy_matches_the_lock() -> None:
    assert _sync().check() == []


def test_a_copy_that_drifts_is_caught(tmp_path: Path) -> None:
    """A guard proved only by passing proves nothing: plant one changed byte."""
    sync = _sync()
    lock = sync.load_lock()
    web = tmp_path / "web"
    for name in lock["files"]:
        (web / name).parent.mkdir(parents=True, exist_ok=True)
        (web / name).write_bytes((WEB / name).read_bytes())
    assert sync.check(web) == []
    page = web / "Board.dc.html"
    page.write_bytes(page.read_bytes() + b" ")
    assert sync.check(web) == ["Board.dc.html: differs from the lock"]
