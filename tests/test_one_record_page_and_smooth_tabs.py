"""One "Our record" page, and pages that do not jump when a tab is clicked.

Cooper, 2026-11-03: "results/season/record/tracker pages all glitch when you
click on them still", and "combine record/tracker into one page for all of the
sports on the website. I want it easier to read for the common person."

Record.dc.html now holds what Tracker.dc.html did, in plain words, plus how
often the win chances came true; Tracker.dc.html sends old links there.
web/smooth_pages.py, run on the published copies, keeps each page hidden until
it is fully drawn and drops the Tracker tab (and the Archive tab the shared
pages would draw in its place) from the shared pages.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SPORT = "epl"
LOCAL = ("Season.dc.html", "Game.dc.html", "Methods.dc.html", "Record.dc.html")


def _smooth():
    spec = importlib.util.spec_from_file_location("smooth_pages", WEB / "smooth_pages.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _published(tmp_path: Path) -> Path:
    for p in WEB.glob("*.dc.html"):
        shutil.copy(p, tmp_path / p.name)
    shutil.copy(WEB / "support.js", tmp_path / "support.js")
    shutil.copytree(WEB / "lib", tmp_path / "lib")
    (tmp_path / "site.json").write_text(json.dumps({"sport": SPORT, "pages": ["season", "record", "tracker", "methods", "game"]}), encoding="utf-8")
    _smooth().smooth(tmp_path)
    return tmp_path


def test_the_tracker_address_sends_its_visitors_to_the_record() -> None:
    text = (WEB / "Tracker.dc.html").read_text(encoding="utf-8")
    assert 'location.replace("Record.dc.html" + location.hash)' in text
    assert 'url=Record.dc.html' in text


def test_the_record_page_reads_both_feeds_and_says_it_plainly() -> None:
    text = (WEB / "Record.dc.html").read_text(encoding="utf-8")
    assert "./data/tracker.json" in text and "./data/record.json" in text
    assert "Our<br>record" in text and "Do our win chances come true?" in text
    assert "is one standard bet" in text
    for jargon in ("Brier", "calibration", "interval:", "ROI"):
        assert jargon not in text, jargon


def test_no_local_page_draws_a_tracker_tab() -> None:
    for page in LOCAL:
        text = (WEB / page).read_text(encoding="utf-8")
        assert '["Tracker", "Tracker.dc.html"]' not in text, page
        assert '["Record", "Record.dc.html"]' in text, page


def test_the_published_shared_pages_end_their_tabs_at_record(tmp_path: Path) -> None:
    out = _published(tmp_path)
    for name in ("Board.dc.html", "Results.dc.html", "Archive.dc.html", "Graphic.dc.html", "lib/sports.js"):
        text = (out / name).read_text(encoding="utf-8")
        assert not re.search(r'hasPage\("tracker"\)|has\("tracker"\) \?', text), name
    for page in out.glob("*.dc.html"):
        if page.name == "Tracker.dc.html":
            continue  # a plain forwarding page, drawn once; nothing to hold back
        head = page.read_text(encoding="utf-8").split("<x-dc", 1)[0]
        assert "sp-wait" in head and "speculationrules" in head, page.name
    # A second run adds nothing.
    assert _smooth().smooth(out) == []


def test_publish_smooths_the_pages_before_naming_the_scripts() -> None:
    wf = (ROOT / ".github/workflows/publish-board.yml").read_text(encoding="utf-8")
    assert wf.index("python web/smooth_pages.py dist") < wf.index("python web/hash_assets.py dist")
    assert wf.index("> dist/site.json") < wf.index("python web/smooth_pages.py dist")
