"""web/hash_assets.py: the published pages load scripts by content-hashed name.

GitHub Pages caches every file for ten minutes and cannot be told otherwise;
naming each script by its bytes makes a longer cache safe. These hold that the
pages and the library's own imports point at the hashed copies, that a changed
file gets a new name, and that the plain names stay for anything linking them.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def _module():
    spec = importlib.util.spec_from_file_location("hash_assets", WEB / "hash_assets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _site(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    shutil.copytree(WEB, dist, ignore=shutil.ignore_patterns("__pycache__", "data", "logos"))
    return dist


def test_every_page_loads_hashed_scripts_and_the_plain_names_stay(tmp_path: Path) -> None:
    dist = _site(tmp_path)
    names = _module().hash_assets(dist)
    assert "lib/sports" in names and "support" in names
    for key, hashed in names.items():
        assert (dist / f"{hashed}.js").is_file() and (dist / f"{key}.js").is_file()
    for page in dist.glob("*.dc.html"):
        refs = re.findall(r"""["'](\./(?:support|lib/[a-z]+)[^"']*\.js)["']""", page.read_text(encoding="utf-8"))
        assert refs, page.name
        for ref in refs:
            assert re.search(r"\.[0-9a-f]{10}\.js$", ref), (page.name, ref)
            assert (dist / ref[2:]).is_file(), (page.name, ref)
    sports = (dist / f"{names['lib/sports']}.js").read_text(encoding="utf-8")
    assert f'from "./{names["lib/format"].split("/")[1]}.js"' in sports


def test_a_changed_library_gets_a_new_name_down_the_chain(tmp_path: Path) -> None:
    before = _module().hash_assets(_site(tmp_path / "a"))
    dist = _site(tmp_path / "b")
    (dist / "lib" / "format.js").write_text((WEB / "lib" / "format.js").read_text(encoding="utf-8") + "\n// changed\n",
                                            encoding="utf-8")
    after = _module().hash_assets(dist)
    assert after["lib/format"] != before["lib/format"]
    assert after["lib/sports"] != before["lib/sports"], "sports.js imports format.js, so its name moves too"
    assert after["lib/live"] == before["lib/live"]
