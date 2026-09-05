"""ClubElo is gone, and the reason is written down rather than re-litigated."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_the_unreachable_fetcher_is_not_back():
    assert not (PROJECT_ROOT / "src/epl_betting_lab/data/fetch_clubelo.py").exists()


def test_nothing_imports_it():
    roots = [PROJECT_ROOT / "src", PROJECT_ROOT / "scripts", PROJECT_ROOT / ".github"]
    scanned: list[Path] = []
    hits = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".yml", ".yaml"} or "egg-info" in path.parts:
                continue
            scanned.append(path)
            if "clubelo" in path.read_text(encoding="utf-8", errors="ignore").lower():
                hits.append(str(path.relative_to(PROJECT_ROOT)))
    # A scan over nothing is green for the wrong reason.
    assert len(scanned) > 100, len(scanned)
    assert any(path.suffix == ".yml" for path in scanned)
    assert not hits, hits


def test_the_decision_is_recorded_with_its_evidence():
    """A future session must be able to see it was tested, not just dropped."""
    doc = (PROJECT_ROOT / "docs/no_external_strength_rating.md").read_text(encoding="utf-8")
    assert "http=000" in doc                      # the actual observation
    assert "37.128.134.74" in doc                 # DNS resolved; TCP did not
    assert "cannot be told apart" in doc          # honest about what is unknown
    assert "GitHub Actions runner" in doc         # how to revisit it properly
