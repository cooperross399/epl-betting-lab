"""The four shared pages and lib/live.js are the same bytes in all three labs.

Board, Results, Archive and Graphic (.dc.html) and lib/live.js are served by
the NHL, EPL and CBB sites from one design, with every NHL-only feature gated
on `sk === "nhl"`. A copy edited in one repo and not the others would ship one
lab's page with another's behaviour. Each repo carries the same manifest,
`web/shared_pages.sha256`, and holds its own copies to it, so a page that
matches its manifest in all three is one page in all three. Change a shared
page by editing it here, copying it out, and regenerating the manifest in
every repo.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
SHARED = ("Board.dc.html", "Results.dc.html", "Archive.dc.html", "Graphic.dc.html", "lib/live.js")


def _manifest() -> dict[str, str]:
    rows = [line.split() for line in (WEB / "shared_pages.sha256").read_text(encoding="utf-8").splitlines() if line.strip()]
    return {name: digest for digest, name in rows}


def test_the_manifest_names_every_shared_file() -> None:
    assert sorted(_manifest()) == sorted(SHARED)


def test_each_shared_file_matches_the_manifest() -> None:
    for name, digest in _manifest().items():
        assert hashlib.sha256((WEB / name).read_bytes()).hexdigest() == digest, name
