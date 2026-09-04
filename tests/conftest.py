"""A guard module that contributed nothing to a run is a red run.

`tests/test_the_guards_exist.py` asserts the hard-rule guard modules are
tracked by git and still define tests. That catches `git rm`. It does not
catch a run that collected them and then ran none of them: `-k`, `-m`,
`--deselect`, `--ignore`, a `collect_ignore` in a conftest, a rename that
leaves the old path in the manifest, or `PYTEST_ADDOPTS` carrying any of those
into a command line that looks clean. Every one of those leaves the suite
green and smaller.

So this hook — registered `trylast`, so it runs AFTER pytest's own `-k` and
`--deselect` handling has removed items — counts, per required module, the
items that survived collection and deselection, and if any required module
contributed zero it ends the session with exit status 1: not a failure inside
one test that a `-k` could also deselect, but the session itself.

Two things are deliberately NOT exemptions:

* `PYTEST_ADDOPTS`. Whatever it holds, every required module is enforced,
  because the environment is exactly where a narrowing hides from a reader of
  the workflow file. The workflow linter refuses the variable in any `env:`
  and in any run block; this is the belt behind that.
* an `addopts` line in the ini configuration, for the same reason.

One thing is: a developer running one module by name. `pytest
tests/test_value.py` on a laptop selects nothing from the guard modules on
purpose, and killing that session would teach everyone to bypass the hook.
The selection is read from the command line ONLY (`invocation_params.args`,
which excludes PYTEST_ADDOPTS), and a required module outside the selection is
not enforced. In CI there is no positional argument — the workflow linter
rejects one — so there every required module is enforced on every run.

Stdlib and pytest only. This must keep working when the package under test is
broken, because that is the run that most needs its guards counted.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

#: The guard modules whose absence from a run is never a pass. Mirrored — and
#: asserted equal — by REQUIRED_GUARDS in tests/test_the_guards_exist.py, so
#: neither list can drift from the other without a red build.
REQUIRED_GUARD_MODULES: tuple[str, ...] = (
    "tests/test_no_secrets_committed.py",
    "tests/test_no_sibling_lab_import.py",
    "tests/test_workflows.py",
    "tests/test_the_guards_exist.py",
)


def _command_line_selection(config: pytest.Config) -> list[Path] | None:
    """The file or directory arguments typed on the command line, resolved.

    `None` when there were none, which is the CI case and means "everything".
    A node id `tests/x.py::test_y` selects the module `tests/x.py`. Option
    values that happen not to start with `-` (`-p no:cacheprovider`, `-k
    expr`) are not paths; anything that does not exist on disk is ignored.
    """
    invocation_dir = Path(config.invocation_params.dir)
    selected: list[Path] = []
    for argument in config.invocation_params.args:
        if argument.startswith("-"):
            continue
        candidate = invocation_dir / argument.split("::", 1)[0]
        if candidate.exists():
            selected.append(candidate.resolve())
    return selected or None


def _is_within(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _enforced_modules(config: pytest.Config) -> list[Path]:
    root = Path(config.rootpath)
    required = [(root / module).resolve() for module in REQUIRED_GUARD_MODULES]
    if os.environ.get("PYTEST_ADDOPTS", "").strip():
        return required
    if str(config.getini("addopts") or "").strip():
        return required
    selection = _command_line_selection(config)
    if selection is None:
        return required
    return [module for module in required if _is_within(module, selection)]


def _end_the_session_if_a_guard_contributed_nothing(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    root = Path(config.rootpath)
    counts = {module: 0 for module in _enforced_modules(config)}
    for item in items:
        try:
            path = Path(item.path).resolve()
        except (OSError, RuntimeError, AttributeError):
            continue
        if path in counts:
            counts[path] += 1
    empty = sorted(
        module.relative_to(root).as_posix()
        for module, count in counts.items()
        if count == 0
    )
    if empty:
        pytest.exit(
            "Required guard module(s) contributed no test to this run: "
            + ", ".join(empty)
            + ". A run that does not execute the hard-rule guards cannot be "
            "green. Remove the -k/-m/--deselect/--ignore/PYTEST_ADDOPTS "
            "narrowing, or restore the module.",
            returncode=1,
        )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    _end_the_session_if_a_guard_contributed_nothing(config, items)


def pytest_collection_finish(session: pytest.Session) -> None:
    """The same count, after EVERY plugin's `pytest_collection_modifyitems`
    has run. `trylast` orders this conftest after pytest's own deselection,
    but a plugin registered before it (a root conftest, `PYTEST_PLUGINS`, a
    `-p` module) also runs its trylast hook after this one, and could
    deselect the guards after they were counted. `session.items` here is the
    list the run loop will execute."""
    _end_the_session_if_a_guard_contributed_nothing(session.config, session.items)
