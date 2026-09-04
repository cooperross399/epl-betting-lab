"""This lab may not reach into a sibling lab, and nothing was checking.

There are five betting labs in this account — NFL, NCAAF, NHL, EPL and college
basketball — one per sport, and they deliberately share no code. Machinery moves
between them by being **ported**: copied into the repository that uses it, where
it is visible and free to diverge as the sport demands.

That was a promise in a docstring until it was broken. The NCAAF lab's venv was
copied from the NFL lab's to save a few minutes of setup, and that installed
`football_betting_lab` into it as an editable package pointing at the sibling
repository. No line of code had to be written for the two labs to be coupled:
any module could have imported it and it would simply have worked, with no
error and no warning, through a path nobody reads.

Two things are asserted, because either alone is insufficient:

* no module here imports a sibling lab — catches a line someone writes;
* no sibling lab is importable from this environment — catches the environment
  making it possible in the first place.

The second is the one that actually bit. A test that only read source would have
passed all day.

Two things this guard used to do quietly and no longer does: it skipped any
module that failed to parse (`except SyntaxError: continue`), so a module
broken on purpose was a module this guard did not read; and it would have
reported green over an empty corpus. An unparseable module is now a failure
that names the file, and the corpus is asserted non-empty. Absence is never a
pass.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: The other four labs. Named individually rather than derived, so a copied
#: venv from ANY of them fails the same way rather than only the one that
#: happened to cause this.
SIBLING_PACKAGES = ("cbb_betting_lab", "football_betting_lab", "ncaaf_betting_lab", "nhl_betting_lab",)

SCANNED_ROOTS = ("src", "scripts", "tests")


def _python_files(project_root: Path = PROJECT_ROOT) -> list[Path]:
    keep: list[Path] = []
    for name in SCANNED_ROOTS:
        root = project_root / name
        if root.is_dir():
            keep.extend(
                p for p in sorted(root.rglob("*.py"))
                if ".venv" not in p.parts and p.name != Path(__file__).name
            )
    return keep


def _sibling_imports(paths: list[Path]) -> list[str]:
    """`file:line: imports name` for every sibling import in `paths`.

    A `SyntaxError` is raised as an `AssertionError` naming the file. It used
    to be `continue`, which made a module that does not parse a module this
    guard had not read — and a guard that skips what it cannot read is a
    guard that can be walked past by breaking the file.
    """
    offenders: list[str] = []
    for path in paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise AssertionError(
                f"{path} does not parse ({exc.msg}, line {exc.lineno}); this guard "
                "cannot read it and refuses to report it clean."
            ) from exc
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".")[0] in SIBLING_PACKAGES:
                    offenders.append(f"{path.name}:{node.lineno}: imports {name}")
    return offenders


def test_the_corpus_is_not_empty() -> None:
    """A guard with nothing to read reports green."""
    files = _python_files()

    assert len(files) > 100, len(files)
    assert any(p.parts[-3:-1] == ("src", "epl_betting_lab") or "epl_betting_lab" in p.parts for p in files)
    assert any(p.parent.name == "scripts" for p in files)
    assert any(p.parent.name == "tests" for p in files)


def test_no_module_imports_a_sibling_lab() -> None:
    files = _python_files()
    assert files, "no Python file found under src/, scripts/ or tests/"

    offenders = _sibling_imports(files)

    assert not offenders, (
        "This lab imports a sibling lab. Machinery is shared by PORTING it "
        "here, visibly, never by coupling two repositories:\n  "
        + "\n  ".join(offenders)
    )


def test_a_sibling_import_is_a_finding(tmp_path: Path) -> None:
    """Positive control: the scanner fires on the thing it hunts."""
    module = tmp_path / "coupled.py"
    module.write_text(
        "import nhl_betting_lab\nfrom football_betting_lab.models import x\n",
        encoding="utf-8",
    )

    assert _sibling_imports([module]) == [
        "coupled.py:1: imports nhl_betting_lab",
        "coupled.py:2: imports football_betting_lab.models",
    ]


def test_a_module_that_does_not_parse_is_a_failure_naming_the_file(tmp_path: Path) -> None:
    """Not `continue`. Breaking the file was a way past this guard."""
    broken = tmp_path / "broken.py"
    broken.write_text("import nhl_betting_lab\ndef (\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="broken.py does not parse"):
        _sibling_imports([broken])


@pytest.mark.parametrize("package", SIBLING_PACKAGES)
def test_no_sibling_lab_is_even_importable(package: str) -> None:
    """The environment half, and the one that actually bit."""
    assert importlib.util.find_spec(package) is None, (
        f"{package} is importable from this environment. A copied venv or a "
        "stray editable install couples two labs through a path nobody reads. "
        f"Uninstall it: `.venv/bin/python -m pip uninstall "
        f"{package.replace('_', '-')}`."
    )


def test_this_lab_s_own_package_is_importable() -> None:
    """The positive control. A guard that passes because nothing is installed
    is not a guard, it is a broken environment."""
    assert importlib.util.find_spec("epl_betting_lab") is not None
