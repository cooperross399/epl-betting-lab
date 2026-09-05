"""A guard module that contributed nothing to a run is a red run, and so is a skip.

`tests/test_the_guards_exist.py` asserts the hard-rule guard modules are
tracked by git and still define tests. That catches `git rm`. It does not
catch a run that collected them and then ran none of them: `-k`, `-m`,
`--deselect`, `--ignore`, a `collect_ignore` in a conftest, a rename that
leaves the old path in the manifest, or `PYTEST_ADDOPTS` carrying any of those
into a command line that looks clean. Every one of those leaves the suite
green and smaller.

Three hooks, because each closes a different route:

* the collection hooks count, per required module, the test FUNCTIONS that
  survived collection and deselection, and compare them against the `def
  test_*` this module reads out of the file with `ast`. A module floor —
  "contributed at least one item" — is what the first version of this file
  enforced, and `--deselect tests/test_no_secrets_committed.py::
  test_env_file_is_never_tracked` walked straight past it: 2004 of 2005
  collected, every required module still non-empty, exit 0 (measured on
  8a50474 with `PYTEST_ADDOPTS` carrying the deselect and `--collect-only`).
  The floor is now per test, so removing one costs the same as removing all.
* `_end_the_session_if_the_run_was_narrowed` asks pytest what it ACTUALLY
  RECEIVED — `config.getoption("deselect")`, `"keyword"`, `"markexpr"`,
  `"ignore"`, `"ignore_glob"`, the ini `addopts` (via `getini`), and `PYTEST_ADDOPTS` — and
  ends the session if any of them is set while a guard is enforced. Reading
  the parsed option rather than the spelling is what makes a `-c other.ini`,
  a `PYTEST_ADDOPTS` assembled from pieces, and a flag typed directly on the
  command line all the same event.
* `pytest_runtest_logreport` and `pytest_collectreport` record every skip.
  `pytest_runtest_logreport` never sees a module-level `pytest.skip(...,
  allow_module_level=True)` or a module-level `pytest.importorskip` — those
  arrive as CollectReports, before any test runs — so a permanent skip on
  data the runner does not have was invisible to a hook that watched only
  test reports. Both are recorded here, and a session with either in it ends
  with status 1.

Two things are deliberately NOT exemptions:

* `PYTEST_ADDOPTS`. Whatever it holds, every required module is enforced,
  because the environment is exactly where a narrowing hides from a reader of
  the workflow file. The workflow linter refuses the variable in any `env:`
  and in any run block; this is the belt behind that.
* an `addopts` line in the ini configuration, for the same reason.

One thing is: a developer running one module by name. `pytest
tests/test_value.py` on a laptop selects nothing from the guard modules on
purpose, and killing that session would teach everyone to bypass the hook.
The selection is read from the POSITIONAL destination pytest parsed
(`file_or_dir`, which is empty when `PYTEST_ADDOPTS` supplied the only
narrowing, and which never confuses an option's value for an argument), and a
required module outside the selection is not enforced; the narrowing check is likewise silent when no guard is
enforced. In CI there is no positional argument — the workflow linter rejects
one — so there every required module is enforced on every run.

The skip gate has no such exemption: a skip is not a pass on a laptop either.

Stdlib and pytest only. This must keep working when the package under test is
broken, because that is the run that most needs its guards counted.
"""

from __future__ import annotations

import ast
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

#: The pytest options that remove tests from a run. Read as pytest PARSED
#: them, so a flag typed on the command line, one arriving through
#: `PYTEST_ADDOPTS`, and one arriving through a `-c` config file are one
#: event with one name.
NARROWING_OPTIONS: tuple[str, ...] = (
    "deselect", "keyword", "markexpr", "ignore", "ignore_glob",
)

#: Every skip seen in this session, as `(kind, nodeid, reason)`. A skip is a
#: test that did not run wearing the name of one that did.
_SKIPS: list[tuple[str, str, str]] = []


def _command_line_selection(config: pytest.Config) -> list[Path] | None:
    """The file or directory arguments, as PYTEST parsed them.

    `None` when there were none, which is the CI case and means "everything".
    A node id `tests/x.py::test_y` selects the module `tests/x.py`.

    Read from `config.getoption("file_or_dir")`, the positional destination,
    rather than by walking `invocation_params.args` and keeping every word
    that names an existing file. That walk could not tell an argument from an
    option's VALUE, and the exemption meant for a developer was reachable by
    anyone: measured on 8a50474, `pytest --collect-only --ignore
    tests/test_books.py -k "not no_secrets_committed"` exited 0 with the
    whole secrets guard deselected, because `tests/test_books.py` — the value
    of `--ignore` — was read as the developer's selection and no guard was
    then enforced at all.

    If the option is not there to read, this returns `None`: everything is
    enforced. A guard that cannot tell what was selected must not conclude
    that nothing was.
    """
    try:
        positional = config.getoption("file_or_dir")
    except (ValueError, AttributeError):
        return None
    if not isinstance(positional, (list, tuple)):
        return None
    invocation_dir = Path(config.invocation_params.dir)
    selected: list[Path] = []
    for argument in positional:
        candidate = invocation_dir / str(argument).split("::", 1)[0]
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


def _declared_test_names(path: Path) -> set[str] | None:
    """Top-level `def test_*` plus `test_*` methods on `Test*` classes, by
    NAME, read with `ast`. `None` when the file cannot be read or parsed —
    which is itself a guard contributing nothing, and is reported as one.

    Names, not a count, because parametrisation multiplies items: one `def`
    with four cases collects as four items sharing one function name, and a
    count would have to guess which.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, ValueError):
        return None
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                names.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name.startswith("test_"):
                        names.add(child.name)
    return names


def _end_the_session_if_a_guard_lost_a_test(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Per required module: every `def test_*` in the file must have
    contributed at least one item to this run."""
    root = Path(config.rootpath)
    enforced = _enforced_modules(config)
    collected: dict[Path, set[str]] = {module: set() for module in enforced}
    for item in items:
        try:
            path = Path(item.path).resolve()
        except (OSError, RuntimeError, AttributeError):
            continue
        if path in collected:
            collected[path].add(str(item.name).split("[", 1)[0])

    empty: list[str] = []
    short: list[str] = []
    unreadable: list[str] = []
    for module in enforced:
        name = module.relative_to(root).as_posix() if module.is_relative_to(root) else str(module)
        declared = _declared_test_names(module)
        if declared is None:
            unreadable.append(name)
            continue
        if not collected[module]:
            empty.append(name)
            continue
        missing = sorted(declared - collected[module])
        if missing:
            short.append(f"{name} ({', '.join(missing)})")

    if unreadable:
        pytest.exit(
            "Required guard module(s) could not be read or parsed: "
            + ", ".join(sorted(unreadable))
            + ". A guard that does not parse contributes nothing, and a run "
            "that cannot read its guards is not a pass.",
            returncode=1,
        )
    if empty:
        pytest.exit(
            "Required guard module(s) contributed no test to this run: "
            + ", ".join(sorted(empty))
            + ". A run that does not execute the hard-rule guards cannot be "
            "green. Remove the -k/-m/--deselect/--ignore/PYTEST_ADDOPTS "
            "narrowing, or restore the module.",
            returncode=1,
        )
    if short:
        pytest.exit(
            "Required guard test(s) did not reach this run: "
            + "; ".join(sorted(short))
            + ". The floor is per TEST, not per module: one guard test "
            "removed is one guard removed. Remove the "
            "-k/-m/--deselect/--ignore/PYTEST_ADDOPTS narrowing, or restore "
            "the test.",
            returncode=1,
        )


def _end_the_session_if_the_run_was_narrowed(config: pytest.Config) -> None:
    """What pytest ACTUALLY RECEIVED, not what the command line spells.

    A narrowing that removes no guard test today removes one tomorrow, and
    the routes in are not enumerable by spelling: `-c other.ini` supplies
    `addopts`, `PYTEST_ADDOPTS` can be assembled from pieces, and a `-k` can
    be typed. All three land in the parsed config, which is what this reads.
    Silent when no guard module is enforced — that is the developer running
    one unrelated module by name.
    """
    if not _enforced_modules(config):
        return
    set_options: list[str] = []
    for option in NARROWING_OPTIONS:
        try:
            value = config.getoption(option)
        except (ValueError, AttributeError):
            continue
        if value:
            set_options.append(f"--{option.replace('_', '-')}={value!r}")
    # `config.inicfg` is the raw ini section and is deprecated in this pytest
    # (accessing it emits a warning into every run); `getini` reads the same
    # `addopts` out of whichever ini file is active, including one supplied by
    # `-c other.ini`, which is the route that has no spelling on the command
    # line worth grepping for.
    ini_addopts = config.getini("addopts")
    if str(ini_addopts or "").strip():
        set_options.append(f"ini addopts={ini_addopts!r}")
    environment = os.environ.get("PYTEST_ADDOPTS", "").strip()
    if environment:
        set_options.append(f"PYTEST_ADDOPTS={environment!r}")
    if set_options:
        pytest.exit(
            "This run was narrowed while the hard-rule guards were enforced: "
            + "; ".join(set_options)
            + ". These were read from the parsed configuration, not from the "
            "command line text, so a config file or an assembled environment "
            "variable is the same event as a typed flag. A narrowed run is "
            "not the run branch protection was promised.",
            returncode=1,
        )


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    _end_the_session_if_a_guard_lost_a_test(config, items)
    _end_the_session_if_the_run_was_narrowed(config)


def pytest_collection_finish(session: pytest.Session) -> None:
    """The same count, after EVERY plugin's `pytest_collection_modifyitems`
    has run. `trylast` orders this conftest after pytest's own deselection,
    but a plugin registered before it (a root conftest, `PYTEST_PLUGINS`, a
    `-p` module) also runs its trylast hook after this one, and could
    deselect the guards after they were counted. `session.items` here is the
    list the run loop will execute."""
    _end_the_session_if_a_guard_lost_a_test(session.config, session.items)
    _end_the_session_if_the_run_was_narrowed(session.config)


def pytest_collectreport(report: pytest.CollectReport) -> None:
    """A module that skipped itself never reaches `pytest_runtest_logreport`.

    `pytest.skip(..., allow_module_level=True)` and a module-level
    `pytest.importorskip` are resolved during COLLECTION and reported here.
    Measured on 8a50474: either one on tests/test_books.py gave `180 passed,
    1 skipped` and exit 0.
    """
    if report.skipped:
        _SKIPS.append(("collection", str(report.nodeid), str(report.longrepr)))


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """A skip raised while the test ran, or by a `skipif`/`skip` marker."""
    if report.skipped:
        _SKIPS.append((str(report.when), str(report.nodeid), str(report.longrepr)))


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """A skip is a test that did not run wearing the name of one that did.

    This lab has none, and the way it keeps having none is that adding one is
    red. `session.exitstatus` is what `wrap_session` returns after this hook,
    so setting it here is the process exit code branch protection reads.
    """
    if not _SKIPS:
        return
    lines = sorted({f"  {kind}: {nodeid}" for kind, nodeid, _ in _SKIPS})
    print(
        "\nThis run skipped "
        + str(len(lines))
        + " item(s). A skip is not a pass: it is a test that did not run "
        "wearing the name of one that did, and a skip on data the runner "
        "does not have is permanent.\n"
        + "\n".join(lines)
    )
    if session.exitstatus == 0:
        session.exitstatus = 1
