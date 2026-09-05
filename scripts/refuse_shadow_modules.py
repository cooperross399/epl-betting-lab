"""Refuse a tracked module that would be imported in place of the test runner.

`python -m pytest` searches the working directory before site-packages, and
the workflow puts `src` on PYTHONPATH ahead of it as well. So a tracked file
called `pytest.py` in either place IS the suite. Measured at c8ebe33, in a
worktree with a two-line tracked `pytest.py` in the repository root:
`PYTHONPATH=src python -m pytest -q` printed one line and exited 0 with no
test reached. On PYTHONPATH it survives the interpreter flag — the same
worktree with `shadow/pytest.py` and
`PYTHONPATH=shadow:src PYTHONSAFEPATH=1 python -m pytest -q` also exited 0
having collected nothing, because PYTHONSAFEPATH drops the working directory
and not PYTHONPATH. `sitecustomize.py` is worse — the
interpreter imports it before it reaches pytest at all, so it can set
PYTEST_ADDOPTS from inside the tree.

tests/test_the_guards_exist.py asserts the same thing. This script exists
because that assertion cannot run: the shadow is what stops the suite from
starting, and a test cannot report a runner that never ran it. So the check
runs as its own step in .github/workflows/tests.yml, BEFORE the suite, with
`PYTHONSAFEPATH=1` set so this script is not reading a tree that has already
replaced its own interpreter's site machinery.

Reads `PYTHONPATH` from the environment rather than taking it as an argument,
so there is no second list to keep in step with the workflow. Exits 1 naming
every offender; exits 1 rather than 0 if `git ls-files` returns nothing,
because a check with no corpus is not a pass.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

#: Names Python imports in preference to the installed distribution.
SHADOWING_BASENAMES = frozenset(
    {"pytest.py", "coverage.py", "sitecustomize.py", "usercustomize.py"}
)

#: Directory names that shadow the same imports as a package.
SHADOWING_DIRECTORY_NAMES = frozenset({"pytest", "_pytest", "coverage"})


def repository_root() -> Path | None:
    """The top level of the repository the WORKING DIRECTORY is in.

    Not `__file__`'s parent: the paths this compares are import roots, and
    those are relative to where the interpreter was started. Running from a
    subdirectory would list only that subtree and call the rest clean, so a
    working directory that is not the top level is refused rather than
    reinterpreted.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def tracked_files() -> list[str]:
    result = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True)
    return [name for name in result.stdout.decode("utf-8").split("\0") if name]


def import_roots() -> list[str]:
    """The repository root (`""`) plus every PYTHONPATH entry, relative."""
    roots = [""]
    for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        entry = entry.strip().strip("/")
        if entry and entry not in roots:
            roots.append(entry)
    return roots


def offenders(tracked: list[str], roots: list[str]) -> list[str]:
    found: list[str] = []
    for name in tracked:
        parts = Path(name).parts
        if parts and parts[-1] in SHADOWING_BASENAMES:
            found.append(name)
            continue
        for root in roots:
            prefix = tuple(part for part in root.split("/") if part)
            if parts[: len(prefix)] != prefix:
                continue
            remainder = parts[len(prefix):]
            if len(remainder) >= 2 and remainder[0] in SHADOWING_DIRECTORY_NAMES:
                found.append(name)
                break
    return sorted(set(found))


def main() -> int:
    top_level = repository_root()
    if top_level is None or top_level.resolve() != Path.cwd().resolve():
        print(
            "::error::this check must run from the top level of the "
            f"repository; git says {top_level!r} and the working directory is "
            f"{Path.cwd()!r}. From a subdirectory it would list part of the "
            "tree and call the rest clean."
        )
        return 1
    tracked = tracked_files()
    if not tracked:
        print(
            "::error::git ls-files returned nothing, so this check looked at "
            "no file. A check with no corpus is not a pass."
        )
        return 1
    roots = import_roots()
    found = offenders(tracked, roots)
    if found:
        print(
            "::error::tracked module(s) Python would import in place of the "
            f"real one, on the import roots {roots}: {found}. `python -m "
            "pytest` would run that file instead of the suite."
        )
        return 1
    print(
        f"No tracked module shadows the test runner on {roots} "
        f"({len(tracked)} tracked files checked)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
